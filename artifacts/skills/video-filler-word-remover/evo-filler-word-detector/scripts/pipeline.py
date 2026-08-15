"""End-to-end pipeline for filler word detection and video extraction."""
import sys
import os
import json

# Ensure script directory is in path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from transcribe import transcribe_video
from detect_fillers import detect_fillers, fillers_to_annotations
from video_edit import extract_and_stitch_fillers, validate_output

def run_pipeline(input_video, annotations_path, output_video,
                 model_name="base", cache_dir=None, padding=0.1):
    """Run the complete filler word detection and extraction pipeline.
    
    Args:
        input_video: Path to input video file
        annotations_path: Path to save annotations JSON
        output_video: Path for output stitched video
        model_name: Whisper model name
        cache_dir: Directory for caching transcripts
        padding: Seconds of padding around filler clips
    """
    # Step 1: Transcribe
    cache_path = None
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "transcript.json")
    
    print("Step 1: Transcribing video...")
    words = transcribe_video(input_video, model_name=model_name, cache_path=cache_path)
    print(f"  Found {len(words)} words")
    
    # Step 2: Detect fillers
    print("Step 2: Detecting filler words...")
    fillers = detect_fillers(words)
    print(f"  Found {len(fillers)} filler instances")
    
    # Step 3: Save annotations
    print("Step 3: Saving annotations...")
    annotations = fillers_to_annotations(fillers)
    with open(annotations_path, 'w') as f:
        json.dump(annotations, f, indent=2)
    print(f"  Saved to {annotations_path}")
    
    # Step 4: Extract and stitch clips
    print("Step 4: Extracting and stitching filler clips...")
    extract_and_stitch_fillers(input_video, fillers, output_video, padding=padding)
    print(f"  Output saved to {output_video}")
    
    # Step 5: Validate
    print("Step 5: Validating output...")
    validate_output(output_video)
    
    return annotations

def validate_deliverables(annotations_path, output_video):
    """Validate all deliverables exist and are well-formed."""
    # Check annotations
    with open(annotations_path, 'r') as f:
        annotations = json.load(f)
    
    assert isinstance(annotations, list), "Annotations must be a list"
    assert len(annotations) > 0, "Annotations must not be empty"
    
    for a in annotations:
        assert "word" in a, f"Missing 'word' key in annotation: {a}"
        assert "timestamp" in a, f"Missing 'timestamp' key in annotation: {a}"
        assert isinstance(a["timestamp"], (int, float)), f"Timestamp must be numeric: {a}"
        assert a["timestamp"] >= 0, f"Timestamp must be non-negative: {a}"
    
    # Check output video
    validate_output(output_video)
    
    print(f"All deliverables validated: {len(annotations)} annotations, output video OK")
    return True


if __name__ == "__main__":
    run_pipeline(
        input_video="/root/input.mp4",
        annotations_path="/root/annotations.json",
        output_video="/root/output.mp4",
        model_name="base",
        cache_dir="/root/cache",
        padding=0.1
    )
