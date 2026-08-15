---
name: evo-hr-diff
description: "Extract employee table from PDF backup, compare with current Excel file, identify deleted and modified employee records, output JSON diff report."
---

# HR Employee Data Diff Skill

Compares an old PDF employee backup with a current Excel employee database to find deletions and modifications.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-hr-diff/scripts')
from utils import generate_diff_report, validate_report

# Generate the diff report
report = generate_diff_report(
    pdf_path='/root/employees_backup.pdf',
    excel_path='/root/employees_current.xlsx',
    output_path='/root/diff_report.json'
)

# Validate
validate_report('/root/diff_report.json')
print(f"Deleted: {len(report['deleted_employees'])}")
print(f"Modified: {len(report['modified_employees'])}")
```

## Functions

- `extract_pdf_table(pdf_path)` - Extract all rows from multi-page PDF, handling repeated headers
- `clean_pdf_dataframe(df)` - Convert PDF string data to proper types (strip commas, cast numerics)
- `load_excel_data(excel_path)` - Load Excel with proper type handling
- `compare_datasets(old_df, new_df, id_col='ID')` - Find deleted IDs and field-level modifications
- `generate_diff_report(pdf_path, excel_path, output_path)` - End-to-end pipeline
- `validate_report(output_path)` - Validate output JSON structure and types

## Key Design Decisions

- PDF is treated as OLD data, Excel as NEW (current)
- Repeated PDF headers on each page are deduplicated
- Salary/Years output as int, Score as float (or int if whole number)
- Text fields compared as stripped strings
- Results sorted by employee ID
