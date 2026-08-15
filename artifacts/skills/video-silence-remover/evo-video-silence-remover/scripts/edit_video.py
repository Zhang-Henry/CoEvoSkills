"""Video editing functions using ffmpeg."""
import subprocess
import os
import json
import tempfile


def build_keep_segments(segments_to_remove, total_duration):
    """Compute complementary keep segments from remove segments."""
    keep = []
    current = 0.0
    for seg_start, seg_end, _ in segments_to_remove:
        if seg_start > current + 0.1:
            keep.append((current, seg_start))
        current = seg_end
    if current < total_duration - 0.1:
        keep.append((current, total_duration))
    return keep


def edit_video_ffmpeg(input_path, output_path, keep_segments,
                     video_codec='libx264', video_preset='fast',
                     audio_codec='aac', audio_bitrate='128k',
                     segment_timeout=300, concat_timeout=300):
    """Create output video by concatenating keep segments.

    Parameters
    ----------
    video_codec, video_preset : str
        Video encoding settings.
    audio_codec, audio_bitrate : str
        Audio encoding settings.
    segment_timeout, concat_timeout : int
        Subprocess timeouts in seconds.
    """
    if not keep_segments:
        raise ValueError("No segments to keep!")

    tmpdir = tempfile.mkdtemp(prefix='video_edit_')
    segment_files = []

    try:
        for i, (start, end) in enumerate(keep_segments):
            seg_file = os.path.join(tmpdir, f'seg_{i:04d}.ts')
            duration = end - start
            cmd = [
                'ffmpeg', '-y',
                '-ss', f'{start:.3f}',
                '-i', input_path,
                '-t', f'{duration:.3f}',
                '-c:v', video_codec, '-preset', video_preset,
                '-c:a', audio_codec, '-b:a', audio_bitrate,
                '-avoid_negative_ts', 'make_zero',
                '-map', '0:v:0', '-map', '0:a:0',
                seg_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=segment_timeout)
            if result.returncode != 0:
                print(f"Warning: segment {i} failed: {result.stderr[:200]}")
                continue
            if os.path.exists(seg_file) and os.path.getsize(seg_file) > 0:
                segment_files.append(seg_file)

        if not segment_files:
            raise RuntimeError("No segments were successfully extracted")

        concat_file = os.path.join(tmpdir, 'concat.txt')
        with open(concat_file, 'w') as f:
            for sf in segment_files:
                f.write(f"file '{sf}'\n")

        cmd = [
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0',
            '-i', concat_file,
            '-c:v', video_codec, '-preset', video_preset,
            '-c:a', audio_codec, '-b:a', audio_bitrate,
            '-movflags', '+faststart',
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True,
                                timeout=concat_timeout)
        if result.returncode != 0:
            raise RuntimeError(f"Concatenation failed: {result.stderr[:500]}")
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Output file was not created or is empty")
    finally:
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


def create_report(original_duration, compressed_duration,
                  segments_to_remove, output_path):
    """Create the compression report JSON.

    Derives removed_duration and compression_percentage from the
    measured original and compressed durations.
    """
    removed = original_duration - compressed_duration
    pct = (removed / original_duration) * 100 if original_duration > 0 else 0
    report = {
        "original_duration_seconds": round(original_duration, 2),
        "compressed_duration_seconds": round(compressed_duration, 2),
        "removed_duration_seconds": round(removed, 2),
        "compression_percentage": round(pct, 2),
        "segments_removed": [
            {
                "start": round(s, 2),
                "end": round(e, 2),
                "duration": round(e - s, 2)
            }
            for s, e, _ in segments_to_remove
        ]
    }
    with open(output_path, 'w') as f:
        json.dump(report, f, indent=2)
    return report
