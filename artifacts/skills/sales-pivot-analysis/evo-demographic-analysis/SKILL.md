---
name: evo-demographic-analysis
description: "Create demographic analysis Excel workbooks with pivot tables from PDF population data and Excel income data. Handles PDF table extraction, data joining on SA2_CODE, quartile binning (equal-width ranges on MEDIAN_INCOME), derived columns, and proper openpyxl pivot table creation with cache fields, pivot fields, and reference lists."
---

# Demographic Analysis Pivot Table Builder

## Overview

This skill creates an Excel workbook with proper pivot tables from two data sources:
- A PDF containing population data by SA2 region (SA2_CODE, SA2_NAME, STATE, POPULATION_2023)
- An Excel file containing income data by SA2 region (SA2_CODE, SA2_NAME, EARNERS, MEDIAN_INCOME, MEAN_INCOME)

## Key Concepts

1. **PDF Extraction**: Multi-page tables with repeated headers, truncated column names
2. **Data Joining**: Inner join on SA2_CODE, filtering 'np' (not publishable) rows
3. **Quartile Binning**: Equal-width range binning on MEDIAN_INCOME (Q1-Q4)
4. **Pivot Tables**: Proper openpyxl pivot table objects with cache fields, pivot fields, row/col/data field references
5. **Derived Columns**: Quarter (from MEDIAN_INCOME ranges) and Total (EARNERS * MEDIAN_INCOME)

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-demographic-analysis/scripts')
from utils import build_workbook, validate_workbook

# Build the workbook
output = build_workbook(
    pdf_path='/root/population.pdf',
    xlsx_path='/root/income.xlsx',
    output_path='/root/demographic_analysis.xlsx'
)

# Validate
errors = validate_workbook('/root/demographic_analysis.xlsx')
if errors:
    print('FAILED:', errors)
else:
    print('SUCCESS')
```

## Functions in scripts/utils.py

- `extract_pdf_table(pdf_path)` - Extract table data from multi-page PDF
- `fix_truncated_headers(headers)` - Fix truncated PDF column headers
- `read_income_data(xlsx_path)` - Read income data from Excel
- `join_data(pop_headers, pop_rows, inc_headers, inc_rows)` - Inner join on SA2_CODE, filter np
- `convert_types(headers, rows)` - Convert string values to numeric types
- `compute_quartile_boundaries(rows, median_income_idx)` - Equal-width quartile boundaries
- `assign_quartile(value, boundaries)` - Assign Q1-Q4 label
- `add_derived_columns(headers, rows, median_income_idx, earners_idx)` - Add Quarter and Total
- `write_source_data_sheet(wb, sheet_name, headers, rows)` - Write enriched data sheet
- `create_pivot_cache(wb, source_ws_name, headers, num_data_rows)` - Create pivot cache
- `create_pivot_table_on_sheet(...)` - Create proper pivot table on a sheet
- `build_workbook(pdf_path, xlsx_path, output_path)` - End-to-end entry point
- `validate_workbook(output_path)` - Validate output meets requirements
