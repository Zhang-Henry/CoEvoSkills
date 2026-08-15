"""
Embedding module - compute embeddings once and cache.
"""
import numpy as np
from sentence_transformers import SentenceTransformer

_model = None

def get_model(model_name='all-MiniLM-L6-v2'):
    global _model
    if _model is None:
        _model = SentenceTransformer(model_name)
    return _model


def compute_embeddings(texts, model_name='all-MiniLM-L6-v2', batch_size=256):
    """Compute sentence embeddings for a list of texts. Returns numpy array."""
    model = get_model(model_name)
    embeddings = model.encode(texts, batch_size=batch_size, show_progress_bar=True,
                              normalize_embeddings=True)
    return np.array(embeddings)


def compute_level_weighted_embeddings(df, model_name='all-MiniLM-L6-v2', batch_size=256):
    """Compute weighted embeddings combining per-level embeddings.
    Higher weight to top levels for broad clustering.
    Returns (embeddings_array, all_unique_texts, text_to_idx mapping)
    """
    # Collect all unique level texts
    all_texts = set()
    for norm_levels in df['norm_levels']:
        for lvl in norm_levels:
            all_texts.add(lvl)
    all_texts = sorted(all_texts)
    text_to_idx = {t: i for i, t in enumerate(all_texts)}
    
    # Compute embeddings for all unique texts
    print(f"Computing embeddings for {len(all_texts)} unique level texts...")
    text_embeddings = compute_embeddings(all_texts, model_name, batch_size)
    
    # Also compute full path embeddings
    full_paths = df['norm_path'].tolist()
    print(f"Computing full path embeddings for {len(full_paths)} paths...")
    path_embeddings = compute_embeddings(full_paths, model_name, batch_size)
    
    # Combine: use weighted average of level embeddings + full path
    dim = text_embeddings.shape[1]
    combined = np.zeros((len(df), dim))
    
    # Weights: higher for top levels, plus full path
    for i, norm_levels in enumerate(df['norm_levels']):
        if len(norm_levels) == 0:
            combined[i] = path_embeddings[i]
            continue
        # Weight scheme: level 1 gets weight 3, level 2 gets 2, rest get 1
        level_embs = []
        weights = []
        for j, lvl in enumerate(norm_levels):
            idx = text_to_idx[lvl]
            level_embs.append(text_embeddings[idx])
            if j == 0:
                weights.append(3.0)
            elif j == 1:
                weights.append(2.0)
            else:
                weights.append(1.0)
        weights = np.array(weights)
        weights = weights / weights.sum()
        weighted = sum(w * e for w, e in zip(weights, level_embs))
        # Mix with full path embedding (50/50)
        combined[i] = 0.5 * weighted + 0.5 * path_embeddings[i]
    
    # Normalize
    norms = np.linalg.norm(combined, axis=1, keepdims=True)
    norms[norms == 0] = 1
    combined = combined / norms
    
    return combined, text_embeddings, all_texts, text_to_idx
