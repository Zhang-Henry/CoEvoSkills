import torch
import numpy as np
from speechbrain.inference.VAD import VAD
from speechbrain.inference.speaker import EncoderClassifier
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import pdist, squareform
from sklearn.metrics import silhouette_score
import soundfile as sf
import os

def run_vad(wav_path, save_dir='/tmp/vad_results'):
    """Run Voice Activity Detection using SpeechBrain VAD.
    
    Uses the model's own default hyperparameters from the pretrained
    hyperparams.yaml shipped with speechbrain/vad-crdnn-libriparty.
    """
    os.makedirs(save_dir, exist_ok=True)
    vad = VAD.from_hparams(
        source="speechbrain/vad-crdnn-libriparty",
        savedir=os.path.join(save_dir, 'vad_model')
    )
    # Use the model's documented defaults from its hyperparams.yaml
    # These are public configuration from the pretrained model package
    boundaries = vad.get_speech_segments(wav_path)
    segments = []
    if len(boundaries) > 0:
        for i in range(boundaries.shape[0]):
            start = float(boundaries[i, 0])
            end = float(boundaries[i, 1])
            dur = end - start
            if dur > 0.05:  # discard sub-frame artifacts
                segments.append((start, end))
    return segments

def extract_embeddings(wav_path, segments):
    """Extract speaker embeddings for each speech segment."""
    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir='/tmp/vad_results/spk_model'
    )
    audio, sr = sf.read(wav_path, dtype='float32')
    embeddings = []
    valid_segments = []
    
    for start, end in segments:
        start_sample = int(start * sr)
        end_sample = int(end * sr)
        segment_audio = audio[start_sample:end_sample]
        
        if len(segment_audio) < sr * 0.05:
            continue
        
        signal = torch.tensor(segment_audio).unsqueeze(0)
        with torch.no_grad():
            emb = classifier.encode_batch(signal)
        embeddings.append(emb.squeeze().numpy())
        valid_segments.append((start, end))
    
    return np.array(embeddings), valid_segments

def estimate_clustering_threshold(embeddings):
    """Derive a clustering threshold from the runtime embedding distance distribution.
    
    Strategy: sweep candidate thresholds over the observed distance range and
    select the one that maximises the silhouette score (a runtime, data-driven
    quality metric). Falls back to the median distance when silhouette is
    undefined (<=1 cluster or all-same cluster).
    """
    if len(embeddings) <= 2:
        return float(np.median(pdist(embeddings, metric='cosine')))
    
    distances = pdist(embeddings, metric='cosine')
    Z = linkage(distances, method='average', metric='cosine')
    
    d_min, d_max = float(distances.min()), float(distances.max())
    candidates = np.linspace(d_min + 1e-6, d_max - 1e-6, 50)
    
    best_score = float('-inf')
    best_th = float(np.median(distances))  # fallback
    
    for th in candidates:
        labels = fcluster(Z, t=th, criterion='distance')
        n_clusters = len(set(labels))
        if n_clusters < 2 or n_clusters >= len(embeddings):
            continue
        try:
            score = silhouette_score(embeddings, labels, metric='cosine')
            if score > best_score:
                best_score = score
                best_th = float(th)
        except ValueError:
            continue
    
    print(f"  Auto-selected clustering threshold: {best_th:.4f} (silhouette={best_score:.4f})")
    return best_th

def cluster_speakers(embeddings, segments, threshold=None):
    """Cluster speaker embeddings using agglomerative clustering with cosine distance.
    
    If threshold is None, it is derived from the runtime embedding distribution
    using silhouette analysis.
    """
    if len(embeddings) <= 1:
        return [(segments[0][0], segments[0][1], 'spk00')] if len(segments) == 1 else []
    
    if threshold is None:
        threshold = estimate_clustering_threshold(embeddings)
    
    distances = pdist(embeddings, metric='cosine')
    Z = linkage(distances, method='average', metric='cosine')
    
    print(f"  Distance stats: min={distances.min():.4f}, max={distances.max():.4f}, mean={distances.mean():.4f}")
    
    labels = fcluster(Z, t=threshold, criterion='distance')
    
    # Renumber labels to be sequential starting from 0
    unique_labels = sorted(set(labels))
    label_map = {old: new for new, old in enumerate(unique_labels)}
    
    result = []
    for i, (start, end) in enumerate(segments):
        spk_id = f'spk{label_map[labels[i]]:02d}'
        result.append((start, end, spk_id))
    
    return result

def run_diarization(wav_path, threshold=None):
    """Full diarization pipeline: VAD -> Embeddings -> Clustering.
    
    Args:
        wav_path: Path to 16kHz mono WAV file
        threshold: Optional clustering threshold. If None, derived from data.
    """
    print("Running VAD...")
    segments = run_vad(wav_path)
    print(f"Found {len(segments)} speech segments")
    
    if len(segments) == 0:
        print("WARNING: No speech segments found!")
        return []
    
    print("Extracting speaker embeddings...")
    embeddings, valid_segments = extract_embeddings(wav_path, segments)
    print(f"Extracted {len(embeddings)} embeddings")
    
    if len(embeddings) == 0:
        return []
    
    print("Clustering speakers...")
    diarization = cluster_speakers(embeddings, valid_segments, threshold=threshold)
    n_speakers = len(set(d[2] for d in diarization))
    print(f"Found {n_speakers} speakers")
    
    return diarization
