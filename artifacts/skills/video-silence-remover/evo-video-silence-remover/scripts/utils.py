"""Utility functions for video silence removal."""
import subprocess
import numpy as np
import json
import os


def extract_audio(video_path, sr=16000):
    """Extract mono audio from video as numpy float32 array."""
    result = subprocess.run(
        ['ffmpeg', '-i', video_path, '-vn', '-ac', '1', '-ar', str(sr),
         '-f', 's16le', '-'],
        capture_output=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr.decode()[:500]}")
    audio = np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32)
    return audio, sr


def extract_frames_grayscale(video_path, fps=2, width=160, height=90):
    """Extract grayscale frames at given fps and resolution."""
    result = subprocess.run(
        ['ffmpeg', '-i', video_path, '-vf', f'fps={fps},scale={width}:{height}',
         '-pix_fmt', 'gray', '-f', 'rawvideo', '-'],
        capture_output=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed: {result.stderr.decode()[:500]}")
    frame_size = width * height
    frames_data = np.frombuffer(result.stdout, dtype=np.uint8)
    num_frames = len(frames_data) // frame_size
    frames = frames_data[:num_frames * frame_size].reshape(num_frames, height, width)
    return frames, fps


def compute_rms_energy(audio, sr, window_sec=0.25):
    """Compute RMS energy in fixed-size windows."""
    window = int(sr * window_sec)
    num_windows = len(audio) // window
    energies = np.array([
        np.sqrt(np.mean(audio[i*window:(i+1)*window]**2))
        for i in range(num_windows)
    ])
    return energies


def compute_frame_diffs(frames):
    """Compute mean absolute frame differences."""
    diffs = np.array([
        np.mean(np.abs(frames[i].astype(float) - frames[i-1].astype(float)))
        for i in range(1, len(frames))
    ])
    return diffs


def get_video_duration(video_path):
    """Get video duration in seconds using ffprobe."""
    result = subprocess.run(
        ['ffprobe', '-v', 'quiet', '-print_format', 'json',
         '-show_format', video_path],
        capture_output=True, text=True, timeout=30
    )
    info = json.loads(result.stdout)
    return float(info['format']['duration'])
