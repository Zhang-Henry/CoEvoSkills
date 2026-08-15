---
name: evo-business-cycle
description: "Calculate Pearson correlation between HP-filtered cyclical components of real PCE and real PFI from ERP tables and CPI data. Use when detrending macroeconomic time series and computing business cycle correlations."
---

# Business Cycle Correlation Skill

This skill extracts nominal PCE and PFI from ERP Excel tables, deflates them
using a CPI index, applies the Hodrick-Prescott filter on log-transformed real
series, and computes the Pearson correlation of the cyclical components.

## Workflow

1. Parse ERP .xls tables to extract annual totals (column 1)
2. For years with only quarterly data, average available quarters
3. Deflate nominal series using CPI (real = nominal / CPI)
4. Take natural logarithm of real series
5. Apply HP filter with specified lambda (100 for annual data)
6. Compute Pearson correlation of cyclical components
7. Write rounded result to output file

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-business-cycle/scripts')
from utils import run_business_cycle_correlation, validate_result

# Run end-to-end
corr = run_business_cycle_correlation(
    pce_filepath='/root/ERP-2025-table10.xls',
    pfi_filepath='/root/ERP-2025-table12.xls',
    cpi_filepath='/root/CPI.xlsx',
    output_filepath='/root/answer.txt',
    start_year=1973,
    end_year=2024,
    hp_lambda=100,
    decimals=5
)

# Validate
validate_result('/root/answer.txt')
```

## Key Functions

- `extract_erp_annual_data(filepath, data_start_row, col_index)` - Parse annual rows from ERP tables
- `extract_erp_quarterly_for_year(filepath, target_year, data_start_row, col_index)` - Get quarterly values for a specific year
- `load_cpi(filepath)` - Load CPI data from xlsx
- `deflate_series(nominal_dict, cpi_dict)` - Convert nominal to real values
- `hp_filter(series_values, lamb)` - Apply HP filter, returns (cycle, trend)
- `compute_correlation(series1, series2)` - Pearson correlation
- `run_business_cycle_correlation(...)` - End-to-end entry point
- `validate_result(output_filepath)` - Validate output file
