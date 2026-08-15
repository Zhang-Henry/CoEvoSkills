---
name: evo-egomotion-analysis
description: "Analyze camera egomotion and detect dynamic objects in video. Classifies camera motion (Stay, Dolly In/Out, Pan Left/Right, Tilt Up/Down, Roll Left/Right) and produces binary masks of independently moving objects. All thresholds are derived from runtime data distributions. Use when given a video file and asked to produce motion labels JSON and dynamic object masks in CSR NPZ format."
---

# Egomotion Analysis and Dynamic Object Segmentation

## Overview

This skill analyzes video to:
1. Classify camera motion (egomotion) into labeled intervals
2. Detect dynamic (independently moving) objects and produce binary masks

All classification and detection thresholds are derived from the runtime data
distribution rather than fixed constants.

## Architecture

### Scripts
- `scripts/video_utils.py` - Frame sampling and optical flow computation
- `scripts/homography_utils.py` - Homography estimation and expected flow
- `scripts/motion_classifier.py` - Motion parameter extraction, noise-floor
  threshold estimation, and camera motion classification
- `scripts/dynamic_segmentation.py` - Dynamic object detection via adaptive
  flow residual thresholding
- `scripts/csr_utils.py` - CSR sparse format encoding/decoding
- `scripts/pipeline.py` - End-to-end pipeline orchestrating all steps

### Pipeline Steps
1. Sample video at caller-supplied target FPS
2. Compute dense optical flow (Farneback) between consecutive sampled frames
3. Estimate homography (ORB + RANSAC) for global camera motion
4. Extract motion parameters (scale, dx, dy, roll) from each homography
5. Derive classification thresholds from the parameter distributions
6. Classify camera motion per frame, smooth temporally, merge into intervals
7. Detect dynamic objects via adaptive residual thresholding and morphological cleanup
8. Apply temporal mask propagation for consistency
9. Save outputs (JSON intervals + CSR NPZ masks)

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-egomotion-analysis/scripts')
from pipeline import run_pipeline, validate_outputs

# All paths and fps are caller-supplied; no defaults embed current-instance paths
intervals, masks = run_pipeline(
    video_path='<path-to-video>',
    target_fps=5,
    json_output='<path-to-output-json>',
    mask_output='<path-to-output-npz>'
)

# Validate
n_frames = len(masks)
shape = masks[0].shape
validate_outputs('<path-to-output-json>', '<path-to-output-npz>', n_frames, shape)
```

## Threshold Derivation

- **Scale threshold**: 2x MAD of scale ratios across all frame pairs
- **Pan threshold**: 2x MAD of |dx| values
- **Tilt threshold**: mean(|dy|) + 2*std(dy), ensuring noise is filtered
- **Roll threshold**: 2.5*std of roll angles from proper homography decomposition
- **Dynamic detection**: median + 3.5*MAD of residual magnitude per frame,
  with a floor of 1.5*median + 1.0
- **Fusion threshold**: derived from nonzero evidence distribution per frame

## Output Formats

### Motion Labels JSON
Intervals are half-open ranges covering indices 0 through N-1, final interval
ends at N. Valid labels: Stay, Dolly In, Dolly Out, Pan Left, Pan Right,
Tilt Up, Tilt Down, Roll Left, Roll Right.

### Dynamic Masks NPZ (CSR format)
- `shape`: [H, W]
- `f_{i}_data`: array of 1s (True pixel values)
- `f_{i}_indices`: column indices of dynamic pixels
- `f_{i}_indptr`: row pointer array (length H+1)

## Key Design Decisions
- Sign inversion: Pan Right = negative dx in image coords
- Roll extracted via cv2.decomposeHomographyMat (translation-dominant solution)
- Adaptive thresholding for dynamic detection based on per-frame residual stats
- Temporal propagation using flow-warped previous masks
- Morphological kernel sizes scaled to image resolution
- Last sampled frame duplicates the previous frame's labels and mask
