import subprocess
import os

def extract_audio(video_path, output_wav, sample_rate=16000):
    """Extract mono 16kHz WAV from video using ffmpeg."""
    cmd = [
        'ffmpeg', '-y', '-i', video_path,
        '-vn', '-acodec', 'pcm_s16le',
        '-ar', str(sample_rate), '-ac', '1',
        output_wav
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr}")
    return output_wav

def get_audio_duration(wav_path):
    """Get audio duration in seconds."""
    import soundfile as sf
    info = sf.info(wav_path)
    return info.duration
