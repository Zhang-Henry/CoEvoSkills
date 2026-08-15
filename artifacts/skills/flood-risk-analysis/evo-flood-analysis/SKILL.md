---
name: evo-flood-analysis
description: "Analyze USGS streamflow stations for flood events by comparing gage height data against NWS flood stage thresholds. Use when detecting flood days for USGS stations over a date range."
---

# Flood Analysis Skill

Detects flooding at USGS stations by:
1. Reading station IDs from input file
2. Fetching NWS flood stage thresholds
3. Retrieving USGS instantaneous gage height data (parameter 00065)
4. Computing daily maximum gage height
5. Comparing daily max against flood stage (>= comparison)
6. Outputting stations with at least one flood day

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-flood-analysis/scripts')
from utils import run_flood_analysis, validate_output

# Run end-to-end analysis
result_df = run_flood_analysis(
    stations_file='/root/data/michigan_stations.txt',
    output_file='/root/output/flood_results.csv',
    start_date='2025-04-01',
    end_date='2025-04-07'
)

# Validate output
validate_output('/root/output/flood_results.csv')
```

## Key Functions

- `read_station_ids(filepath)` - Read station IDs from text file
- `fetch_nws_flood_stages()` - Download NWS flood thresholds
- `fetch_gage_height_data(station_id, start, end)` - Get USGS gage height IV data
- `compute_daily_max(gage_df)` - Resample to daily max
- `count_flood_days(daily_max, flood_stage)` - Count days >= threshold
- `run_flood_analysis(stations_file, output_file, start, end)` - End-to-end pipeline
- `validate_output(output_file)` - Validate output CSV

## Domain Notes

- Uses gage height (00065), NOT discharge (00060)
- Daily max is the standard aggregation for flood assessment
- Flood day: daily max gage height >= NWS flood stage
- Station IDs must be preserved as strings (leading zeros)
- Only stations with valid NWS flood stage thresholds are analyzed
- Output sorted by flood_days descending
