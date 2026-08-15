---
name: evo-rar-analysis
description: "Build Reserves-at-Risk workbook from IMF commodity data and reserve templates."
---

# Reserves at Risk Analysis

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-rar-analysis/scripts')
from utils import run_end_to_end, validate_workbook

run_end_to_end(
    template_path='/root/data/test-rar.xlsx',
    imf_path='/root/data/external-data.xlsx',
    output_path='/root/output/rar_result.xlsx',
    z_score=1.65,
    avg_price_max_month=9,
)
validate_workbook('/root/output/rar_result.xlsx')
```

`z_score` and `avg_price_max_month` come from the task instruction.
All other structure is discovered at runtime from the template workbook.
