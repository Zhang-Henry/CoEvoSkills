---
name: evo-mario-counter
description: "Extract keyframes from a Super Mario video, convert to grayscale, count coins/enemies/turtles using template matching with NMS and SQDIFF filtering, and output CSV results. Use when given a video file with template images for object counting."
---

# Video Object Counter for Super Mario

This skill extracts codec keyframes (I-frames) from a video, converts them to grayscale,
counts objects (coins, enemies, turtles) using template matching with non-maximum suppression,
and writes a CSV summary.

## Key Insights

- Extract only I-frames (codec keyframes) using ffmpeg's `select=eq(pict_type,I)` filter
- Convert frames to grayscale INPLACE before template matching
- Template matching uses `TM_CCOEFF_NORMED` with per-object thresholds
- **Critical**: For coins, also use `TM_SQDIFF_NORMED` to filter out structurally similar
  but visually different objects (e.g., question mark blocks vs coins). CCOEFF_NORMED is
  invariant to brightness shifts, so it gives false positives for question blocks. SQDIFF
  catches the absolute pixel difference.
- Non-maximum suppression prevents double-counting nearby detections
- HUD/UI elements at the top of the screen can cause false positives with small templates
- Thresholds: coins CCOEFF>=0.75 AND SQDIFF<=0.15, enemies CCOEFF>=0.80, turtles CCOEFF>=0.85

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-mario-counter/scripts')
from utils import run_full_pipeline, validate_output

# Run the full pipeline
df = run_full_pipeline(
    video_path='/root/super-mario.mp4',
    output_dir='/root',
    template_paths={
        'coin': '/root/coin.png',
        'enemy': '/root/enemy.png',
        'turtle': '/root/turtle.png'
    },
    csv_output_path='/root/counting_results.csv',
    coin_threshold=0.75,
    enemy_threshold=0.80,
    turtle_threshold=0.85,
    coin_sqdiff_threshold=0.15,
    debug=True
)

# Validate
issues = validate_output('/root/counting_results.csv', '/root')
if issues:
    print(f"Issues found: {issues}")
else:
    print("All checks passed!")
```

## Functions

- `extract_keyframes(video_path, output_dir, prefix)` - Extract I-frames using ffmpeg
- `convert_to_grayscale_inplace(image_path)` - Convert image to grayscale and overwrite
- `count_objects(frame_path, template_path, threshold, debug, use_sqdiff_filter, sqdiff_threshold)` - Count with template matching + NMS + optional SQDIFF filter
- `nms_detections(detections, min_dist_x, min_dist_y)` - Non-maximum suppression
- `run_full_pipeline(...)` - End-to-end pipeline
- `validate_output(csv_path, output_dir, prefix)` - Validate output files and CSV
