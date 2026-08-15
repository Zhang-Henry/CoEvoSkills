"""Utility functions for multilingual dubbing pipeline.

All functions are parameterized - no hardcoded paths or instance-specific values.
"""
import os
import re
import json
import subprocess
import numpy as np
import warnings
warnings.filterwarnings('ignore')


def parse_srt_file(filepath):
    """Parse an SRT file and return list of segments with start_sec, end_sec, text.
    Works with any valid SRT file regardless of number of entries.
    """
    import pysrt
    subs = pysrt.open(filepath)
    segments = []
    for sub in subs:
        start_sec = sub.start.hours * 3600 + sub.start.minutes * 60 + sub.start.seconds + sub.start.milliseconds / 1000.0
        end_sec = sub.end.hours * 3600 + sub.end.minutes * 60 + sub.end.seconds + sub.end.milliseconds / 1000.0
        text = sub.text.strip()
        segments.append({
            'index': sub.index,
            'start_sec': start_sec,
            'end_sec': end_sec,
            'text': text
        })
    return segments


def read_target_language(filepath):
    """Read target language code from file."""
    with open(filepath, 'r') as f:
        return f.read().strip()


def detect_source_language(source_text):
    """Detect source language from text content using character distribution heuristics."""
    if not source_text:
        return 'en'
    ascii_count = sum(1 for c in source_text if ord(c) < 128)
    total = max(len(source_text), 1)
    # CJK character ranges
    jp_count = sum(1 for c in source_text if '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff' or '\u4e00' <= c <= '\u9fff')
    zh_count = sum(1 for c in source_text if '\u4e00' <= c <= '\u9fff')
    ko_count = sum(1 for c in source_text if '\uac00' <= c <= '\ud7af')
    
    if ko_count / total > 0.1:
        return 'ko'
    if jp_count / total > 0.1:
        # Distinguish Japanese from Chinese by presence of hiragana/katakana
        kana = sum(1 for c in source_text if '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff')
        if kana > 0:
            return 'ja'
        return 'zh'
    if zh_count / total > 0.1:
        return 'zh'
    if ascii_count / total > 0.7:
        return 'en'
    # Check for common non-ASCII Latin scripts
    latin_ext = sum(1 for c in source_text if '\u00c0' <= c <= '\u024f')
    if (ascii_count + latin_ext) / total > 0.7:
        return 'en'  # or could be fr/es/de - default to en
    return 'en'


def get_kokoro_lang_code(lang):
    """Map ISO 639-1 language code to Kokoro pipeline lang_code.
    Kokoro uses single-letter codes for its language pipelines.
    """
    mapping = {
        'ja': 'j',
        'en': 'a',  # American English
        'zh': 'z',
        'fr': 'f',
        'es': 'e',
        'hi': 'h',
        'it': 'i',
        'pt': 'p',
        'ko': 'k',
    }
    return mapping.get(lang, 'a')


def get_kokoro_default_voice(lang):
    """Get a default Kokoro voice name for the given ISO 639-1 language code.
    Voice naming convention: {lang_prefix}{gender}_{name}
    where lang_prefix matches Kokoro's internal language codes.
    """
    # Map language to a known voice - these are publicly documented Kokoro voices
    mapping = {
        'ja': 'jf_alpha',
        'en': 'af_heart',
        'zh': 'zf_xiaobei',
        'fr': 'ff_siwis',
        'es': 'ef_dora',
        'hi': 'hf_alpha',
        'it': 'if_sara',
        'pt': 'pf_dora',
    }
    return mapping.get(lang, 'af_heart')


def discover_available_voices(repo_id='hexgrad/Kokoro-82M', lang_prefix=None):
    """Discover available voices from the Kokoro model repository.
    Optionally filter by language prefix (e.g., 'jf' for Japanese female).
    """
    try:
        from huggingface_hub import list_repo_tree
        files = list(list_repo_tree(repo_id, path_in_repo='voices'))
        voices = []
        for f in files:
            name = f.path.replace('voices/', '').replace('.pt', '')
            if lang_prefix is None or name.startswith(lang_prefix):
                voices.append(name)
        return voices
    except Exception:
        return []


def synthesize_tts(text, lang_code, voice, speed=1.0):
    """Synthesize speech using Kokoro TTS.
    
    Args:
        text: Text to synthesize
        lang_code: Kokoro language code (e.g., 'j' for Japanese)
        voice: Voice name (e.g., 'jf_alpha')
        speed: Speech speed multiplier (higher = faster)
    
    Returns:
        (audio_array, sample_rate) tuple. Audio is float32 numpy array.
        Kokoro's native sample rate is 24000 Hz.
    """
    from kokoro import KPipeline
    pipeline = KPipeline(lang_code=lang_code, repo_id='hexgrad/Kokoro-82M')
    
    all_audio = []
    for result in pipeline(text, voice=voice, speed=speed):
        audio = result.audio
        if hasattr(audio, 'numpy'):
            audio = audio.numpy()
        else:
            audio = np.array(audio)
        all_audio.append(audio)
    
    if not all_audio:
        raise RuntimeError(f"TTS produced no audio for text: {text[:50]}")
    
    combined = np.concatenate(all_audio)
    native_sr = 24000
    return combined, native_sr


def resample_audio(audio, orig_sr, target_sr):
    """Resample audio to target sample rate using scipy."""
    if orig_sr == target_sr:
        return audio
    from scipy.signal import resample as scipy_resample
    num_samples = int(len(audio) * target_sr / orig_sr)
    resampled = scipy_resample(audio, num_samples)
    return resampled.astype(np.float32)


def rate_adjust_audio(audio, sr, target_duration):
    """Adjust audio duration by resampling to match target_duration.
    This changes the playback speed without changing pitch significantly
    for small adjustments.
    """
    current_duration = len(audio) / sr
    if current_duration <= 0 or target_duration <= 0:
        return audio
    
    rate_factor = current_duration / target_duration
    target_samples = int(len(audio) / rate_factor)
    from scipy.signal import resample as scipy_resample
    adjusted = scipy_resample(audio, target_samples)
    return adjusted.astype(np.float32)


def ensure_mono(audio):
    """Ensure audio is mono. If multi-dimensional, average channels."""
    if audio.ndim > 1:
        audio = np.mean(audio, axis=-1)
    return audio.astype(np.float32)


def normalize_audio_peak(audio, target_peak=0.9):
    """Normalize audio to target peak level."""
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio * (target_peak / peak)
    return audio


def measure_lufs_from_file(filepath):
    """Measure integrated LUFS of an audio/video file using ffmpeg ebur128 filter.
    
    IMPORTANT: Returns the SUMMARY integrated loudness (last I: LUFS match),
    not per-frame values. The ebur128 filter outputs per-frame I: values that
    converge over time, followed by a final summary block. The summary value
    is the correct integrated loudness.
    """
    cmd = [
        'ffmpeg', '-i', filepath,
        '-af', 'ebur128=peak=true',
        '-f', 'null', '-'
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    stderr = result.stderr
    
    # Iterate all lines, keep the LAST match - that's the summary
    lufs = None
    for line in stderr.split('\n'):
        if 'I:' in line and 'LUFS' in line:
            match = re.search(r'I:\s*(-?[\d.]+)\s*LUFS', line)
            if match:
                lufs = float(match.group(1))
    
    return lufs


def normalize_to_lufs(audio, sr, target_lufs=-23.0):
    """Normalize audio array to target LUFS using measure-then-adjust approach."""
    import soundfile as sf
    import tempfile
    
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp_path = tmp.name
    
    try:
        sf.write(tmp_path, audio, sr, subtype='FLOAT')
        current_lufs = measure_lufs_from_file(tmp_path)
        
        if current_lufs is None:
            return normalize_audio_peak(audio, 0.5)
        
        gain_db = target_lufs - current_lufs
        gain_linear = 10 ** (gain_db / 20.0)
        
        adjusted = audio * gain_linear
        
        # Prevent clipping
        peak = np.max(np.abs(adjusted))
        if peak > 0.99:
            adjusted = adjusted * (0.99 / peak)
        
        return adjusted
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def save_wav(audio, sr, filepath):
    """Save audio array to WAV file."""
    import soundfile as sf
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    sf.write(filepath, audio, sr, subtype='FLOAT')


def get_video_duration(filepath):
    """Get video duration in seconds using ffprobe."""
    cmd = [
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        filepath
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return float(result.stdout.strip())


def create_full_audio_track(segments_audio, video_duration, sr):
    """Create a full-length audio track with speech segments placed at their positions.
    
    Args:
        segments_audio: list of dicts with 'start_sec' and 'audio' (numpy array at sr)
        video_duration: total video duration in seconds
        sr: sample rate
    
    Returns:
        numpy array of the full audio track (silence where no speech)
    """
    total_samples = int(video_duration * sr)
    full_audio = np.zeros(total_samples, dtype=np.float32)
    
    for seg in segments_audio:
        start_sample = int(seg['start_sec'] * sr)
        audio = seg['audio']
        
        # Clip to track length
        available = total_samples - start_sample
        if available <= 0:
            continue
        if len(audio) > available:
            audio = audio[:available]
        
        full_audio[start_sample:start_sample + len(audio)] = audio
    
    return full_audio


def mux_audio_video(video_path, audio_path, output_path, sr):
    """Mux audio into video, copying video stream and encoding audio as AAC."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cmd = [
        'ffmpeg', '-y',
        '-i', video_path,
        '-i', audio_path,
        '-c:v', 'copy',
        '-c:a', 'aac',
        '-ar', str(sr),
        '-ac', '1',
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-shortest',
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg mux failed: {result.stderr}")
    return output_path


def compute_utmos_score(audio, sr):
    """Compute UTMOS quality score for audio.
    UTMOS expects 16kHz mono input. Returns score on 1-5 scale.
    Scores > 3.5 indicate broadcast-acceptable quality.
    """
    import torch
    
    if sr != 16000:
        audio_16k = resample_audio(audio, sr, 16000)
    else:
        audio_16k = audio
    
    audio_16k = ensure_mono(audio_16k)
    
    model = torch.hub.load('tarepan/SpeechMOS:v1.2.0', 'utmos22_strong', trust_repo=True)
    tensor = torch.from_numpy(audio_16k).unsqueeze(0).float()
    score = model(tensor, 16000)
    return score.item()


def generate_report(source_lang, target_lang, sr, channels, orig_duration, new_duration,
                    measured_lufs, speech_segments, output_path):
    """Generate the dubbing report JSON file."""
    report = {
        'source_language': source_lang,
        'target_language': target_lang,
        'audio_sample_rate_hz': sr,
        'audio_channels': channels,
        'original_duration_sec': round(orig_duration, 2),
        'new_duration_sec': round(new_duration, 2),
        'measured_lufs': round(measured_lufs, 1) if measured_lufs is not None else None,
        'speech_segments': speech_segments
    }
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    return report


def choose_duration_strategy(tts_duration, window_duration, max_rate_ratio=2.0):
    """Choose the best duration control strategy based on TTS vs window duration.
    
    Args:
        tts_duration: Duration of raw TTS output in seconds
        window_duration: Target window duration in seconds
        max_rate_ratio: Maximum acceptable rate adjustment ratio
    
    Returns:
        str: 'rate_adjust', 'pad_silence', or 'trim'
    """
    ratio = tts_duration / window_duration
    
    if ratio <= max_rate_ratio and ratio >= (1.0 / max_rate_ratio):
        return 'rate_adjust'
    elif tts_duration < window_duration:
        return 'pad_silence'
    else:
        return 'trim'


def compute_optimal_tts_speed(raw_tts_duration, window_duration, min_speed=0.7, max_speed=1.5):
    """Compute optimal Kokoro speed parameter to minimize post-synthesis rate adjustment.
    
    The idea: if raw TTS at speed=1.0 produces duration D, then at speed=S it produces
    approximately D/S. We want D/S ≈ window_duration, so S ≈ D/window_duration.
    Clamp to reasonable bounds to maintain speech quality.
    """
    if window_duration <= 0:
        return 1.0
    ideal_speed = raw_tts_duration / window_duration
    return max(min_speed, min(max_speed, ideal_speed))
