---
name: evo-gdp-weighted-mean
description: "Skill for populating Excel workbooks with INDEX/MATCH lookup formulas, net export percentage calculations, descriptive statistics, and GDP-weighted mean using SUMPRODUCT. Use when a task requires filling in economic data from a source sheet using two-key lookups and computing trade statistics."
---

# GDP Weighted Mean Calculation Skill

This skill handles Excel workbooks that require:
1. Two-key lookups (series code + year) using INDEX/MATCH
2. Net exports as % of GDP calculations
3. Descriptive statistics (min, max, median, mean, percentiles)
4. GDP-weighted mean using SUMPRODUCT

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-gdp-weighted-mean/scripts')
from utils import run_end_to_end

# Run the complete workflow
run_end_to_end('/root/gdp.xlsx')
```

## Functions

### `run_end_to_end(input_path, output_path=None)`
Complete workflow: discovers layout, writes all formulas, saves, recalculates with LibreOffice, and validates.

### `discover_task_layout(wb)`
Discovers the Task sheet structure at runtime: year row, export/import/GDP rows, net export rows, statistics rows.

### `discover_data_layout(wb)`
Discovers the Data sheet structure: header row, series code column, year columns, data range.

### `write_lookup_formulas(wb, task_layout, data_layout)`
Writes INDEX/MATCH formulas for two-key lookups (series code + year).

### `write_net_export_formulas(wb, task_layout)`
Writes (Exports - Imports) / GDP * 100 formulas.

### `write_statistics_formulas(wb, task_layout)`
Writes MIN, MAX, MEDIAN, AVERAGE, PERCENTILE formulas.

### `write_weighted_mean_formula(wb, task_layout)`
Writes SUMPRODUCT-based weighted mean formula.

### `validate_workbook(filepath)`
Checks that all expected cells contain formulas.

### `validate_calculated_values(filepath)`
After LibreOffice recalculation, checks for formula errors like #REF!, #NAME?, etc.
