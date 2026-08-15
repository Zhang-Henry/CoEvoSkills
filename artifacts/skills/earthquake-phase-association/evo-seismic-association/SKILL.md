---
name: evo-seismic-association
description: "Seismic phase association pipeline: loads MSEED waveforms and station CSV, runs SeisBench PhaseNet for P/S picking, associates picks into earthquake events using greedy time-clustering with travel-time corrections, and outputs event catalog CSV. Use when task involves earthquake detection, phase picking, or seismic event association."
---

# Seismic Phase Association Skill

End-to-end pipeline for detecting earthquake events from seismic waveform data.

## Components

- **data_loader.py**: Load MSEED waveforms, parse station CSV, group traces by station
- **picker.py**: Run SeisBench PhaseNet deep learning model for P/S phase picking
- **associator.py**: Associate picks into events using greedy P-pick clustering with travel-time origin estimation
- **pipeline.py**: Orchestrate the full workflow and validate output

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-seismic-association/scripts')
from pipeline import run_pipeline, validate_results

# Run the full pipeline
events_df = run_pipeline(
    mseed_path='/root/data/wave.mseed',
    stations_csv_path='/root/data/stations.csv',
    output_csv_path='/root/results.csv',
    p_threshold=0.3,
    s_threshold=0.3,
    vp=6.0,
    vs_ratio=1.75,
    max_p_spread=10.0,
    min_stations=3,
    assumed_depth_km=8.0,
    dedup_window=5.0,
    model_name='instance'
)

# Validate output
validate_results('/root/results.csv')
print(f"Detected {len(events_df)} events")
```

## Algorithm Details

### Phase Picking
- Uses SeisBench PhaseNet with pretrained weights
- Processes each station independently with 3-component (E/N/Z) data
- Channel preference: HH > HN > EH
- Default thresholds: P=0.3, S=0.3

### Association
1. Sort all P picks chronologically
2. Greedy grouping: consecutive P picks within `max_p_spread` seconds form a group
3. Filter groups requiring `min_stations` unique stations
4. For each group, estimate origin time by subtracting travel time (distance/vp) from each pick
5. Use median of origin time estimates as event time
6. Deduplicate events within `dedup_window` seconds, keeping the one with most stations

### Travel Time Model
- Uniform velocity: vp (default 6 km/s), vs = vp / vs_ratio
- Distance: haversine great-circle + assumed depth (3D distance)
- Origin time = pick_time - (distance_3d / velocity)

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| p_threshold | 0.3 | PhaseNet P-phase detection threshold |
| s_threshold | 0.3 | PhaseNet S-phase detection threshold |
| vp | 6.0 | P-wave velocity (km/s) |
| vs_ratio | 1.75 | vp/vs ratio |
| max_p_spread | 10.0 | Max seconds between first and last P pick in group |
| min_stations | 3 | Minimum stations for valid event |
| assumed_depth_km | 8.0 | Assumed source depth (km) |
| dedup_window | 5.0 | Seconds window for merging duplicate events |

## Output Format

CSV with columns:
- `time`: Event origin time in ISO format without timezone (e.g., 2019-07-04T19:00:11.708)
- `n_stations`: Number of stations that detected the event
- `n_picks`: Number of P picks in the event group
- `mean_prob`: Mean pick probability
