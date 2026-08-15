---
name: evo-filler-word-detector
description: "Detect filler words in interview videos using Whisper ASR with word-level timestamps, classify disfluencies, save annotations as JSON, and extract/stitch filler clips into an output video. Use when a task requires finding hesitation markers (um, uh, like, you know, etc.) in video/audio and producing both timestamp annotations and a compiled filler-word video."
---

# Filler Word Detector

Detects filler words and phrases in video using OpenAI Whisper for transcription
with word-level timestamps, then classifies disfluencies and produces:
1. A JSON annotations file with detected fillers and timestamps
2. A stitched video of all filler word clips

## Supported Filler Words
- Non-lexical: um, uh, hum, hmm, mhm
- Discourse markers: like, yeah, so, basically, well, okay
- Multi-word: you know, i mean, kind of, i guess

## Scripts

- `scripts/transcribe.py` - Whisper transcription with word-level timestamps and caching
- `scripts/detect_fillers.py` - Filler word/phrase detection with overlap handling
- `scripts/video_edit.py` - FFmpeg-based clip extraction and concatenation
- `scripts/pipeline.py` - End-to-end orchestration

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-filler-word-detector/scripts')
from pipeline import run_pipeline, validate_deliverables

# Run the full pipeline
run_pipeline(
    input_video="/root/input.mp4",
    annotations_path="/root/annotations.json",
    output_video="/root/output.mp4",
    model_name="base",
    cache_dir="/root/cache",
    padding=0.1
)

# Validate deliverables
validate_deliverables("/root/annotations.json", "/root/output.mp4")
```

## Component Usage

### Transcription
```python
from transcribe import transcribe_video
words = transcribe_video("/root/input.mp4", model_name="base", cache_path="/root/cache/transcript.json")
# Returns: [{"word": "hello", "start": 0.0, "end": 0.5}, ...]
```

### Filler Detection
```python
from detect_fillers import detect_fillers, fillers_to_annotations
fillers = detect_fillers(words)
# Returns: [{"word": "um", "timestamp": 3.5, "start": 3.4, "end": 3.7}, ...]
annotations = fillers_to_annotations(fillers)
# Returns: [{"word": "um", "timestamp": 3.5}, ...]
```

### Video Editing
```python
from video_edit import extract_and_stitch_fillers, validate_output
extract_and_stitch_fillers("/root/input.mp4", fillers, "/root/output.mp4", padding=0.1)
validate_output("/root/output.mp4")
```

## Design Notes

- Multi-word phrases are matched greedily (longest first) before single words
- Words used in multi-word phrases are excluded from single-word matching
- Overlapping detections are removed (earlier detection kept)
- Transcripts are cached to avoid re-running Whisper inference
- Video clips use re-encoding for frame-accurate cuts
- Clip padding adds context around each filler word
