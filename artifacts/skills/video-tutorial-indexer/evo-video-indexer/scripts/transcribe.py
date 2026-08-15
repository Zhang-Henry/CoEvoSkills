import whisper
import json
import subprocess
import os

def extract_audio(video_path, audio_path="/tmp/audio.wav"):
    """Extract audio from video using ffmpeg."""
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path, "-y"
    ], capture_output=True)
    return audio_path

def transcribe_audio(audio_path, model_name="base"):
    """Transcribe audio using Whisper and return timestamped segments."""
    model = whisper.load_model(model_name)
    result = model.transcribe(audio_path, language="en", verbose=False)
    segments = []
    for seg in result["segments"]:
        segments.append({
            "start": round(seg["start"], 2),
            "end": round(seg["end"], 2),
            "text": seg["text"].strip()
        })
    return segments

def save_transcript(segments, output_path):
    """Save transcript segments to JSON."""
    with open(output_path, "w") as f:
        json.dump(segments, f, indent=2)
    return output_path
