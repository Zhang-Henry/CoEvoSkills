---
name: evo-seismic-picker
description: "Seismic phase picking using PhaseNet deep learning model via SeisBench. Normalizes waveform data, handles single-channel traces by replication, runs PhaseNet classify(), auto-calibrates probability thresholds from data, and falls back to metadata-based travel time picks when PhaseNet fails."
---

# evo-seismic-picker

Seismic phase picking skill using PhaseNet (SeisBench) for P and S wave arrival detection.

## Approach
1. Load each trace's 3-component waveform data
2. Reorder channels to ZNE orientation
3. Handle single-channel data by replicating active channel to all 3 components
4. Normalize data by dividing by max absolute value (critical for PhaseNet)
5. Create ObsPy Stream with proper metadata
6. Auto-calibrate probability thresholds from a data sample (or accept caller-supplied)
7. Run PhaseNet classify() to get P and S picks
8. Select best picks per trace (highest probability, S must follow P)
9. For files where PhaseNet finds no picks, fall back to metadata-based travel time computation
10. Write results to CSV with file_name, phase, pick_idx columns

## Key Insights
- PhaseNet requires normalized data to produce picks (raw physical units are extremely small)
- Single-channel stations need signal replicated to all 3 components
- Accelerometer data works fine without integration when normalized
- Probability thresholds are calibrated from data sample, not hardcoded
- Metadata fallback uses caller-supplied Vp and Vp/Vs ratio with hypocentral distance

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-seismic-picker/scripts')
from utils import process_all_files

# Run full pipeline - thresholds auto-calibrated from data
df = process_all_files('/root/data/', '/root/results.csv')

# Or supply explicit thresholds and velocity model
df = process_all_files('/root/data/', '/root/results.csv',
                       p_threshold=0.3, s_threshold=0.3,
                       vp=6.0, vs_ratio=1.73)
```

## Key Functions
- `load_trace(filepath)` - Load npz trace file with metadata
- `prepare_zne_normalized(data, channels)` - Reorder to ZNE, handle single-channel, normalize
- `make_obspy_stream(zne_data, dt, start_time_str)` - Convert to ObsPy Stream
- `calibrate_thresholds(data_dir, model, sample_size)` - Derive thresholds from data
- `metadata_based_pick(trace_info, vp, vs_ratio)` - Compute P/S indices from metadata
- `pick_with_phasenet(stream, model, dt, start_time_str, p_threshold, s_threshold)` - Run PhaseNet
- `select_best_picks(picks)` - Select best P and S from candidates
- `process_all_files(data_dir, output_csv, ...)` - Full end-to-end pipeline
