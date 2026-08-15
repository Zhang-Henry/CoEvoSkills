---
name: evo-lake-warming
description: "Analyze lake surface water temperature trends and attribute warming to driver categories using Mann-Kendall trend test with year-based Sen slope, and per-category R-squared importance. All mappings derived at runtime."
---

# Lake Warming Trend & Attribution Skill

## Overview
1. **Trend Analysis**: Mann-Kendall test for p-value + year-based Theil-Sen slope
2. **Driver Attribution**: Per-category R² from linear regression, normalized to 100%

## Runtime Column Classification
Predictor columns classified by keyword matching on column names:
- **Heat**: airtemp, shortwave, longwave, radiation, solar, etc.
- **Flow**: precip, inflow, outflow, discharge, streamflow, etc.
- **Wind**: wind, gust
- **Human**: developed, agriculture, urban, impervious, landuse, etc.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-lake-warming/scripts')
from utils import run_end_to_end, validate_outputs

results = run_end_to_end(
    data_dir='/root/data',
    output_dir='/root/output',
    target_file_keyword='temperature',
    join_key='Year'
)
print(results)
validate_outputs('/root/output')
```

## Functions
- `load_and_merge(data_dir, target_file_keyword, join_key)` — load and merge CSVs
- `compute_trend(df, time_col, target_col)` — MK p-value + year-based Sen slope
- `classify_column(col_name)` — keyword-based category assignment
- `build_category_map(predictor_cols)` — classify all predictors
- `compute_attribution(df, target_col, time_col)` — per-category R² importance
- `run_end_to_end(data_dir, output_dir, ...)` — full pipeline
- `validate_outputs(output_dir)` — check output files
