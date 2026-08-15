---
name: evo-proteomics-workbook
description: "Fills a proteomics Task sheet with INDEX-MATCH expression lookups, group statistics (AVERAGE/STDEV for Control vs Treated), and fold change formulas (Log2FC and FC). Discovers layout at runtime from the workbook itself. Use when a protein_expression.xlsx has Task and Data sheets requiring two-way lookups and differential expression calculations."
---

# Proteomics Workbook Skill

This skill automates filling a proteomics analysis workbook with formulas:

1. **Expression Lookups** (C11:L20): INDEX-MATCH formulas to pull values from Data sheet
2. **Group Statistics** (B24:K27): AVERAGE and STDEV for Control and Treated groups
3. **Fold Change** (rows 32-41): Log2 FC = Treated Mean - Control Mean; FC = 2^(Log2FC)

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-proteomics-workbook/scripts')
from utils import run_end_to_end

success = run_end_to_end('/root/protein_expression.xlsx')
if success:
    print('Task completed successfully')
else:
    print('Validation failed - check errors above')
```

## Key Functions

- `discover_task_layout(ws_task)` - Discovers proteins, samples, groups, and cell ranges
- `discover_data_layout(ws_data)` - Builds protein-row and sample-column indices
- `write_expression_formulas(ws_task, task_layout, data_layout)` - INDEX-MATCH formulas
- `write_statistics_formulas(ws_task, task_layout)` - AVERAGE/STDEV per protein per group
- `write_fold_change_formulas(ws_task, task_layout)` - Log2FC and FC formulas
- `recalculate_with_libreoffice(filepath)` - Headless recalculation
- `validate_workbook(filepath)` - Checks all output cells for numeric values
- `run_end_to_end(input_path, output_path=None)` - Full pipeline

## Design Notes

- All layouts discovered at runtime from the workbook
- Formulas reference cells, not hard-coded values
- Statistics reference expression cells in the Task sheet
- Control/Treated group membership read from row 9
- LibreOffice recalculates cached formula values
- Validation checks for formula errors (#REF!, #NAME?, etc.)
