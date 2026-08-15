---
name: evo-pedestrian-counter
description: "Count unique pedestrians in surveillance videos using YOLOv8 detection and multi-object tracking. Deduplicates across frames, excludes cyclists. Writes per-video counts to Excel."
---

# Pedestrian Counter for Surveillance Videos

## Problem

Given a directory of surveillance-camera video files, count the number
of unique pedestrians (people travelling on foot) in each video and
write the per-video counts to a structured Excel workbook.

## Approach

1. **Detect** persons with YOLO (COCO class 0).
2. **Track** across frames so each physical person gets one ID.
3. **Filter** noise tracks shorter than a visibility window derived
   from the video's own frame rate.
4. **Exclude cyclists** via person-bicycle bounding-box overlap.
5. **Write** to Excel via openpyxl.

## Scripts

| File | Key function |
|------|--------|
| `scripts/utils.py` | `get_video_files`, `count_pedestrians_in_video`, `write_results_to_excel` |
| `scripts/run_pipeline.py` | `run_pipeline(video_dir, output_path, sheet_name, col_filename, col_count)` |
| `scripts/validate.py` | `validate_output(output_path, video_dir, sheet_name, col_filename, col_count)` |

## Runnable Fresh-Agent Example

Adapt the five variables below to the current task instruction.

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-pedestrian-counter/scripts')

from run_pipeline import run_pipeline
from validate import validate_output

# ---- set from the current task instruction ----
video_dir   = '/path/to/input/videos'
output_path = '/path/to/output.xlsx'
sheet_name  = 'data'
col_file    = 'source'
col_count   = 'total'
# -----------------------------------------------

results = run_pipeline(video_dir, output_path,
                       sheet_name=sheet_name,
                       col_filename=col_file,
                       col_count=col_count)

ok, issues = validate_output(output_path, video_dir,
                             sheet_name=sheet_name,
                             col_filename=col_file,
                             col_count=col_count)
if not ok:
    raise RuntimeError(issues)
print('Done:', results)
```

## How It Works

- A **fresh YOLO model** is created per video to reset tracker state.
- **Sampling interval**: derived as `max(1, round(fps / 10))` so that
  roughly ten frames per second are processed regardless of source fps.
- **Minimum-detection threshold**: derived as `max(2, round(fps * 0.5 / sample_every))`
  so a person must be observed for at least half a second.
- **Cyclist exclusion**: person tracks that spatially overlap a bicycle
  track in the majority of co-occurring frames are removed.
- COCO class indices 0 (person) and 1 (bicycle) are public taxonomy.
