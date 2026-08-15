"""End-to-end pipeline for video silence removal."""
import sys
import os
import json

scripts_dir = os.path.dirname(os.path.abspath(__file__))
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from utils import (extract_audio, extract_frames_grayscale,
                   get_video_duration)
from detect_segments import get_segments_to_remove
from edit_video import build_keep_segments, edit_video_ffmpeg, create_report


def run_pipeline(input_video, output_video, report_path,
                 window_sec=0.25, min_pause_sec=2.0,
                 local_window_sec=30.0, block_sec=5.0,
                 context_sec=5.0, min_drop_ratio=0.6,
                 refine_sec=3.0):
    """End-to-end video silence removal.

    Parameters are forwarded to detection functions; see their
    docstrings for semantics.  All decision thresholds are derived
    from the input data at runtime.
    """
    print(f"[Pipeline] Input: {input_video}")
    original_duration = get_video_duration(input_video)
    print(f"[Pipeline] Original duration: {original_duration:.2f}s")

    print("[Pipeline] Extracting audio...")
    audio, sr = extract_audio(input_video)

    print("[Pipeline] Extracting frames...")
    frames, fps = extract_frames_grayscale(input_video)

    print("[Pipeline] Detecting segments to remove...")
    segments, opening_end = get_segments_to_remove(
        audio, sr, frames, fps,
        window_sec=window_sec, min_pause_sec=min_pause_sec,
        local_window_sec=local_window_sec, block_sec=block_sec,
        context_sec=context_sec, min_drop_ratio=min_drop_ratio,
        refine_sec=refine_sec)

    print(f"[Pipeline] Opening end: {opening_end:.2f}s")
    total_removed = 0
    for s, e, d in segments:
        print(f"  Remove: {s:.2f}s - {e:.2f}s ({d:.2f}s)")
        total_removed += d
    print(f"[Pipeline] Total to remove: {total_removed:.2f}s")

    keep = build_keep_segments(segments, original_duration)
    print(f"[Pipeline] Keep segments: {len(keep)}")

    print("[Pipeline] Editing video...")
    edit_video_ffmpeg(input_video, output_video, keep)

    compressed_duration = get_video_duration(output_video)
    print(f"[Pipeline] Compressed duration: {compressed_duration:.2f}s")

    print("[Pipeline] Creating report...")
    report = create_report(original_duration, compressed_duration,
                           segments, report_path)
    print(f"[Pipeline] Compression: {report['compression_percentage']:.1f}%")
    print("[Pipeline] Done!")
    return report


def validate_output(output_video, report_path):
    """Validate output files. Returns (ok, issues)."""
    issues = []
    for path, label in [(output_video, 'video'), (report_path, 'report')]:
        if not os.path.exists(path):
            issues.append(f"{label} not found: {path}")
    if issues:
        return False, issues

    try:
        actual_dur = get_video_duration(output_video)
        if actual_dur <= 0:
            issues.append("Output video has non-positive duration")
    except Exception as e:
        issues.append(f"Cannot read output video: {e}")

    try:
        with open(report_path) as f:
            rpt = json.load(f)
        for k in ('original_duration_seconds', 'compressed_duration_seconds',
                  'removed_duration_seconds', 'compression_percentage',
                  'segments_removed'):
            if k not in rpt:
                issues.append(f"Missing key: {k}")
        if not issues:
            o, c, r = (rpt['original_duration_seconds'],
                       rpt['compressed_duration_seconds'],
                       rpt['removed_duration_seconds'])
            if abs((o - c) - r) > 1.0:
                issues.append(f"Math: {o}-{c} != {r}")
            ep = (r / o) * 100 if o > 0 else 0
            if abs(rpt['compression_percentage'] - ep) > 1.0:
                issues.append(f"Pct mismatch")
            segs = rpt['segments_removed']
            if not isinstance(segs, list):
                issues.append("segments_removed not a list")
            else:
                for i, seg in enumerate(segs):
                    for k2 in ('start', 'end', 'duration'):
                        if k2 not in seg:
                            issues.append(f"Seg {i} missing {k2}")
                    if all(k2 in seg for k2 in ('start', 'end', 'duration')):
                        if seg['start'] < 0:
                            issues.append(f"Seg {i} negative start")
                        if seg['end'] <= seg['start']:
                            issues.append(f"Seg {i} end<=start")
                        if abs(seg['duration'] - (seg['end'] - seg['start'])) > 0.1:
                            issues.append(f"Seg {i} dur mismatch")
            if actual_dur > 0 and abs(c - actual_dur) > 2.0:
                issues.append(f"Duration mismatch: report={c} actual={actual_dur}")
    except json.JSONDecodeError:
        issues.append("Invalid JSON")
    except Exception as e:
        issues.append(str(e))
    return len(issues) == 0, issues


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('input_video')
    p.add_argument('output_video')
    p.add_argument('report_path')
    p.add_argument('--window-sec', type=float, default=0.25)
    p.add_argument('--min-pause-sec', type=float, default=2.0)
    a = p.parse_args()
    run_pipeline(a.input_video, a.output_video, a.report_path,
                 a.window_sec, a.min_pause_sec)
    ok, iss = validate_output(a.output_video, a.report_path)
    print('OK' if ok else f'Issues: {iss}')
