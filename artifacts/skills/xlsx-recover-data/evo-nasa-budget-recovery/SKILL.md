---
name: evo-nasa-budget-recovery
description: "Recover missing values marked with '???' in NASA budget Excel workbooks. Analyzes cross-sheet relationships (totals, YoY changes, shares, growth analysis) to derive missing numeric values. Includes LibreOffice recalculation."
---

# NASA Budget Recovery Skill

Recovers missing values in multi-sheet NASA budget workbooks where values are marked with '???'.

## Approach

1. **Budget by Directorate**: Use Total = sum(components) to recover missing components or totals
2. **YoY Changes (%)**: Use formula `100*(current-previous)/previous` with budget values
3. **Directorate Shares (%)**: Use formula `100*component/total` with budget values
4. **Growth Analysis**: Compute CAGR, differences, and averages from budget values
5. **Cross-sheet resolution**: When a budget row has 2 unknowns, use YoY percentages to recover one, then derive the other from the total
6. **Recalculation**: Use LibreOffice to recalculate the workbook after recovery

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-nasa-budget-recovery/scripts')
from utils import run_full_pipeline

input_path = '/root/nasa_budget_incomplete.xlsx'
output_path = '/root/nasa_budget_recovered.xlsx'

issues = run_full_pipeline(input_path, output_path)
if not issues:
    print("All validations passed!")
```

## Key Functions

- `run_full_pipeline(input_path, output_path)` - Complete end-to-end pipeline with recalculation
- `run_recovery(input_path, output_path)` - Recovery without recalculation
- `validate_recovery(output_path)` - Validate all constraints are satisfied
- `recalculate_with_engine(output_path)` - Recalculate with LibreOffice
- `recover_budget_values(wb)` - Solve budget totals/components
- `recover_from_yoy(wb, budget_recovered)` - Use YoY to fill budget gaps
- `recover_shares(wb, budget_recovered)` - Compute share percentages
- `recover_growth(wb, budget_recovered)` - Compute growth metrics
