"""Validation functions for dubbing pipeline output.

All functions are parameterized - no hardcoded paths or instance-specific values.
"""
import os
import json
import subprocess
import re
import warnings
warnings.filterwarnings('ignore')


def validate_dubbing_output(output_dir, target_sr=48000, target_channels=1,
                            target_lufs=-23.0, lufs_tolerance=3.0,
                            start_tolerance=0.01, drift_tolerance=0.2):
    """Validate all dubbing outputs meet requirements.
    
    Args:
        output_dir: Directory containing outputs
        target_sr: Expected sample rate
        target_channels: Expected channel count
        target_lufs: Expected LUFS target
        lufs_tolerance: Acceptable LUFS deviation
        start_tolerance: Max seconds between placed_start and window_start
        drift_tolerance: Max absolute drift in seconds
    
    Returns:
        (passed, issues) tuple
    """
    issues = []
    
    # Discover segment files dynamically
    tts_dir = os.path.join(output_dir, 'tts_segments')
    if not os.path.isdir(tts_dir):
        issues.append(f"Missing directory: {tts_dir}")
    else:
        seg_files = sorted([f for f in os.listdir(tts_dir) if f.startswith('seg_') and f.endswith('.wav')])
        if not seg_files:
            issues.append(f"No segment WAV files found in {tts_dir}")
        for sf_name in seg_files:
            seg_path = os.path.join(tts_dir, sf_name)
            info = get_audio_info(seg_path)
            if info:
                if info.get('sample_rate') != target_sr:
                    issues.append(f"{sf_name} sample rate is {info.get('sample_rate')}, expected {target_sr}")
                if info.get('channels') != target_channels:
                    issues.append(f"{sf_name} channels is {info.get('channels')}, expected {target_channels}")
                
                lufs = measure_lufs(seg_path)
                if lufs is not None and abs(lufs - target_lufs) > lufs_tolerance:
                    issues.append(f"{sf_name} LUFS is {lufs:.1f}, expected near {target_lufs}")
    
    # Check dubbed video
    dubbed_path = os.path.join(output_dir, 'dubbed.mp4')
    if not os.path.exists(dubbed_path):
        issues.append(f"Missing: {dubbed_path}")
    else:
        vinfo = get_video_info(dubbed_path)
        if vinfo:
            if vinfo.get('audio_sample_rate') != target_sr:
                issues.append(f"dubbed.mp4 audio SR is {vinfo.get('audio_sample_rate')}, expected {target_sr}")
            if vinfo.get('audio_channels') != target_channels:
                issues.append(f"dubbed.mp4 audio channels is {vinfo.get('audio_channels')}, expected {target_channels}")
    
    # Check report
    report_path = os.path.join(output_dir, 'report.json')
    if not os.path.exists(report_path):
        issues.append(f"Missing: {report_path}")
    else:
        with open(report_path, 'r') as f:
            report = json.load(f)
        
        required_fields = ['source_language', 'target_language', 'audio_sample_rate_hz',
                          'audio_channels', 'original_duration_sec', 'new_duration_sec',
                          'measured_lufs', 'speech_segments']
        for field in required_fields:
            if field not in report:
                issues.append(f"report.json missing field: {field}")
        
        if report.get('audio_sample_rate_hz') != target_sr:
            issues.append(f"report SR is {report.get('audio_sample_rate_hz')}, expected {target_sr}")
        if report.get('audio_channels') != target_channels:
            issues.append(f"report channels is {report.get('audio_channels')}, expected {target_channels}")
        
        if 'speech_segments' in report:
            for i, seg in enumerate(report['speech_segments']):
                seg_fields = ['window_start_sec', 'window_end_sec', 'placed_start_sec',
                             'placed_end_sec', 'source_text', 'target_text',
                             'window_duration_sec', 'tts_duration_sec', 'drift_sec',
                             'duration_control']
                for field in seg_fields:
                    if field not in seg:
                        issues.append(f"segment {i} missing field: {field}")
                
                if 'placed_start_sec' in seg and 'window_start_sec' in seg:
                    diff = abs(seg['placed_start_sec'] - seg['window_start_sec'])
                    if diff > start_tolerance:
                        issues.append(f"segment {i}: placed_start differs by {diff:.3f}s (>{start_tolerance}s)")
                
                if 'drift_sec' in seg and abs(seg['drift_sec']) > drift_tolerance:
                    issues.append(f"segment {i}: drift is {seg['drift_sec']:.3f}s (>{drift_tolerance}s)")
                
                valid_controls = ['rate_adjust', 'pad_silence', 'trim']
                if 'duration_control' in seg and seg['duration_control'] not in valid_controls:
                    issues.append(f"segment {i}: invalid duration_control: {seg['duration_control']}")
    
    return len(issues) == 0, issues


def get_audio_info(filepath):
    """Get audio file info using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=sample_rate,channels',
            '-of', 'json',
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        stream = data.get('streams', [{}])[0]
        return {
            'sample_rate': int(stream.get('sample_rate', 0)),
            'channels': int(stream.get('channels', 0))
        }
    except Exception:
        return None


def get_video_info(filepath):
    """Get video file audio info using ffprobe."""
    try:
        cmd = [
            'ffprobe', '-v', 'error',
            '-select_streams', 'a:0',
            '-show_entries', 'stream=sample_rate,channels',
            '-of', 'json',
            filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        stream = data.get('streams', [{}])[0]
        return {
            'audio_sample_rate': int(stream.get('sample_rate', 0)),
            'audio_channels': int(stream.get('channels', 0))
        }
    except Exception:
        return None


def measure_lufs(filepath):
    """Measure integrated LUFS. Returns SUMMARY value (last I: LUFS match)."""
    try:
        cmd = [
            'ffmpeg', '-i', filepath,
            '-af', 'ebur128=peak=true',
            '-f', 'null', '-'
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        lufs = None
        for line in result.stderr.split('\n'):
            if 'I:' in line and 'LUFS' in line:
                match = re.search(r'I:\s*(-?[\d.]+)\s*LUFS', line)
                if match:
                    lufs = float(match.group(1))
        return lufs
    except Exception:
        return None
