---
name: evo-dots-calculator
description: "Calculate Dots coefficients for IPF powerlifting data. Copies relevant columns from Data sheet to Dots sheet, adds TotalKg and Dots formulas. Use when computing normalized strength scores for powerlifting competitions."
---

# Dots Calculator Skill

## Overview
Calculates Dots coefficients for International Powerlifting Federation (IPF) competition data.
The Dots formula normalizes total lifted weight by bodyweight and sex.

## Workflow
1. Identify columns needed: Name, Sex, BodyweightKg, Best3SquatKg, Best3BenchKg, Best3DeadliftKg
2. Copy these columns to Dots sheet (preserving original order and names)
3. Append TotalKg column with Excel formula (sum of three lifts)
4. Append Dots column with Excel formula using sex-dependent polynomial coefficients

## Dots Formula
Dots = TotalKg * 500 / (A*bw^4 + B*bw^3 + C*bw^2 + D*bw + E)

Male coefficients: A=-0.000001093, B=0.0007391293, C=-0.1918759221, D=24.0900756, E=-307.75076
Female coefficients: A=-0.0000010706, B=0.0005158568, C=-0.1126655495, D=13.6175032, E=-57.96288

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-dots-calculator/scripts')
from utils import run_dots_pipeline, validate_dots_workbook

# Run the full pipeline
run_dots_pipeline('/root/data/openipf.xlsx')

# Validate the output
validate_dots_workbook('/root/data/openipf.xlsx')
```

## Key Functions
- `get_dots_columns()` - Returns list of column names needed for Dots
- `find_column_indices(header_row, column_names)` - Maps column names to indices
- `copy_columns_to_dots(wb)` - Copies relevant columns from Data to Dots sheet
- `add_totalkg_formula(ws_dots, sorted_cols, max_row)` - Adds TotalKg Excel formula column
- `add_dots_formula(ws_dots, sorted_cols, max_row, total_col)` - Adds Dots Excel formula column
- `run_dots_pipeline(input_path, output_path)` - End-to-end entry point
- `validate_dots_workbook(path)` - Validates structure and formulas
