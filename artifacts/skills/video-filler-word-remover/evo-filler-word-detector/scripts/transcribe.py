"""Transcribe audio from video using OpenAI Whisper with word-level timestamps."""
import whisper
import json
import os

def transcribe_video(video_path, model_name="base", cache_path=None):
    """Transcribe video and return word-level timestamps.
    
    Args:
        video_path: Path to input video file
        model_name: Whisper model size (tiny, base, small, medium, large)
        cache_path: Optional path to cache transcript JSON
    
    Returns:
        List of dicts with 'word', 'start', 'end' keys
    """
    # Check cache first
    if cache_path and os.path.exists(cache_path):
        with open(cache_path, 'r') as f:
            return json.load(f)
    
    model = whisper.load_model(model_name)
    result = model.transcribe(
        video_path,
        word_timestamps=True,
        language="en"
    )
    
    words = []
    for segment in result["segments"]:
        if "words" in segment:
            for w in segment["words"]:
                words.append({
                    "word": w["word"].strip(),
                    "start": round(w["start"], 3),
                    "end": round(w["end"], 3)
                })
    
    # Cache result
    if cache_path:
        with open(cache_path, 'w') as f:
            json.dump(words, f, indent=2)
    
    return words
