import whisper
import soundfile as sf
import numpy as np

def transcribe_segments(wav_path, diarization_segments, model_name='small'):
    """Transcribe each diarized segment using Whisper.
    
    Args:
        wav_path: Path to 16kHz mono WAV
        diarization_segments: list of (start, end, spk_id) tuples
        model_name: Whisper model size (auto-detected from cache at runtime)
    """
    print(f"Loading Whisper model '{model_name}'...")
    model = whisper.load_model(model_name)
    
    audio, sr = sf.read(wav_path, dtype='float32')
    
    results = []
    for start, end, spk_id in diarization_segments:
        start_sample = int(start * sr)
        end_sample = int(end * sr)
        segment_audio = audio[start_sample:end_sample]
        
        if len(segment_audio) < sr * 0.05:
            continue
        
        # Pad very short segments so whisper has enough context
        min_samples = int(sr * 0.5)
        if len(segment_audio) < min_samples:
            segment_audio = np.pad(segment_audio, (0, min_samples - len(segment_audio)))
        
        # Use whisper defaults; model internally manages speech detection
        result = model.transcribe(
            segment_audio,
            language=None,
            fp16=False,
            condition_on_previous_text=False
        )
        
        text = result['text'].strip()
        if text:
            results.append({
                'start': start,
                'end': end,
                'speaker': spk_id,
                'text': text
            })
            print(f"  [{start:.2f}-{end:.2f}] {spk_id}: {text}")
    
    return results
