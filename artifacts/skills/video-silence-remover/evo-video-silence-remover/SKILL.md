---
name: evo-video-silence-remover
description: "Remove silence and non-teaching content from teaching videos. Detects openings and pauses using data-driven audio energy and visual frame-difference analysis. Produces a compressed video and JSON compression report."
---

# Video Silence Remover Skill

## Overview

Removes non-teaching content (openings, pauses) from teaching videos by
combining audio energy analysis with visual frame differencing. All decision
thresholds are derived from the input data distribution at runtime.

## Scripts

- `scripts/utils.py` – audio/frame extraction, RMS energy, frame diffs, duration queries
- `scripts/detect_segments.py` – opening and pause detection with data-driven thresholds
- `scripts/edit_video.py` – ffmpeg segment extraction, concatenation, report generation
- `scripts/run_pipeline.py` – end-to-end orchestration and output validation

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-video-silence-remover/scripts')
from run_pipeline import run_pipeline, validate_output

report = run_pipeline(
    input_video='data/input_video.mp4',
    output_video='compressed_video.mp4',
    report_path='compression_report.json',
    window_sec=0.25,
    min_pause_sec=2.0,
)

ok, issues = validate_output('compressed_video.mp4', 'compression_report.json')
if ok:
    print("All checks passed!")
else:
    for issue in issues:
        print(f"Issue: {issue}")
```

## How It Works

### Opening Detection

1. Extracts grayscale frames and computes mean absolute differences per block.
2. Derives a static-vs-active threshold from the frame-diff distribution
   using a gap-analysis method on the sorted lower half of block means.
3. Identifies the contiguous truly-static prefix from the video start.
4. Searches for the largest relative audio energy drop near the static
   boundary to locate the transition into teaching content.
5. Refines the boundary to the nearest local energy minimum.

### Pause Detection

Three complementary strategies scan the teaching portion of the audio:

- **Adaptive local windows** – compares energy to a threshold derived
  from local and global statistics so that quiet teaching regions do
  not mask pauses.
- **Global percentile** – uses the midpoint of the 10th and 25th
  percentiles of the teaching-content energy distribution.
- **Running-median ratio** – flags sustained dips below a data-derived
  fraction of the smoothed energy baseline.

Detections from all strategies are merged.

### Video Editing

- Computes keep intervals as the complement of remove intervals.
- Extracts each keep segment to an intermediate transport-stream file.
- Concatenates via the ffmpeg concat demuxer with re-encoding.
- Measures the actual output duration for accurate report values.

### Report

The JSON report contains original, compressed, and removed durations,
a compression percentage, and a list of removed segments with start,
end, and duration fields.  Removed duration and percentage are derived
from the measured original and compressed durations.

## Parameters

All parameters have defaults justified by signal-processing conventions
and are exposed as function arguments:

| Parameter | Default | Purpose |
|---|---|---|
| `window_sec` | 0.25 | RMS energy analysis window |
| `min_pause_sec` | 2.0 | Minimum pause duration to remove |
| `local_window_sec` | 30.0 | Local context for adaptive thresholds |
| `block_sec` | 5.0 | Frame-diff averaging block size |
| `context_sec` | 5.0 | Context for energy-drop detection |
| `min_drop_ratio` | 0.6 | Max after/before ratio for transitions |
| `refine_sec` | 3.0 | Boundary refinement search radius |
