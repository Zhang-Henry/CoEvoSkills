"""Extract filler word clips and stitch them into a single video."""
import subprocess
import os
import tempfile

def get_video_duration(video_path):
    """Get video duration in seconds."""
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", video_path],
        capture_output=True, text=True
    )
    import json
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])

def extract_and_stitch_fillers(video_path, fillers, output_path, padding=0.1):
    """Extract filler word clips and concatenate them into one video.
    
    Args:
        video_path: Path to source video
        fillers: List of dicts with 'start' and 'end' keys
        output_path: Path for output concatenated video
        padding: Seconds of padding around each filler clip
    """
    if not fillers:
        raise ValueError("No fillers detected to extract")
    
    duration = get_video_duration(video_path)
    
    # Build filter_complex for precise cutting and concatenation
    # Use trim/atrim filters for frame-accurate cuts
    tmpdir = tempfile.mkdtemp()
    
    # Create individual clips
    clip_files = []
    for i, f in enumerate(fillers):
        start = max(0, f["start"] - padding)
        end = min(duration, f["end"] + padding)
        clip_path = os.path.join(tmpdir, f"clip_{i:04d}.mp4")
        
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-ss", str(start),
            "-to", str(end),
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            "-map", "0:v:0", "-map", "0:a:0",
            clip_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Warning: Failed to extract clip {i}: {result.stderr[-200:]}")
            continue
        if os.path.exists(clip_path) and os.path.getsize(clip_path) > 0:
            clip_files.append(clip_path)
    
    if not clip_files:
        raise RuntimeError("No clips were successfully extracted")
    
    # Create concat file
    concat_file = os.path.join(tmpdir, "concat.txt")
    with open(concat_file, 'w') as f:
        for cf in clip_files:
            f.write(f"file '{cf}'\n")
    
    # Concatenate using concat demuxer
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "aac",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Concatenation failed: {result.stderr[-500:]}")
    
    # Cleanup
    for cf in clip_files:
        os.remove(cf)
    if os.path.exists(concat_file):
        os.remove(concat_file)
    os.rmdir(tmpdir)
    
    return output_path

def validate_output(output_path):
    """Validate the output video exists and has valid streams."""
    if not os.path.exists(output_path):
        raise FileNotFoundError(f"Output not found: {output_path}")
    
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", output_path],
        capture_output=True, text=True
    )
    import json
    info = json.loads(result.stdout)
    
    dur = float(info["format"]["duration"])
    if dur <= 0:
        raise ValueError(f"Output has zero/negative duration: {dur}")
    
    stream_types = {s["codec_type"] for s in info["streams"]}
    if "video" not in stream_types:
        raise ValueError("Output missing video stream")
    if "audio" not in stream_types:
        raise ValueError("Output missing audio stream")
    
    print(f"Output validated: {dur:.2f}s, streams: {stream_types}")
    return True
