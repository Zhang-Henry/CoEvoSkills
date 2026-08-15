---
name: evo-supply-shock
description: "Supply-side shock analysis using Cobb-Douglas production function to estimate potential GDP impact of investment spending shock on a small open economy. Collects data from PWT, IMF WEO, and ECB, implements HP filter via LibreOffice Solver, and builds Excel model."
---

# Supply-Side Shock Analysis Skill

## Overview
This skill implements a complete workflow for estimating the impact of an investment spending shock on a small open economy using:
1. Data collection from PWT (capital stock), IMF WEO (GDP), and ECB (CFC)
2. HP filter for trend extraction in Excel
3. Cobb-Douglas production function for potential GDP estimation
4. Investment shock modeling

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-supply-shock/scripts')
from data_collection import collect_pwt_data, collect_weo_data, collect_ecb_cfc_data
from excel_builder import build_supply_model
from validator import validate_workbook

# End-to-end entry point
build_supply_model(
    template_path='/root/test-supply.xlsx',
    output_path='/root/test-supply.xlsx'
)

# Validate
validate_workbook('/root/test-supply.xlsx')
```

## Workflow Steps
1. **Data Collection**: Download PWT, WEO, ECB data programmatically
2. **Populate PWT Sheet**: Fill rnna and rgdpna columns
3. **Populate WEO Sheet**: Fill real GDP level and growth rate, extend to 2043
4. **Populate CFC Sheet**: Fill CFC data, link capital stock, calculate depreciation
5. **Production Sheet**: Set up HP filter formulas, production function
6. **Run LibreOffice Solver**: Optimize HP filter via macro
7. **Validate**: Check formulas and results
