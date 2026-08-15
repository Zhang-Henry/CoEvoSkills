---
name: evo-demand-shock
description: "Build a demand-side macroeconomic investment shock analysis workbook for a small open economy. Fetches IMF WEO data and country supply-use tables, calculates import content share, and produces multi-scenario Excel output with formulas."
---

# Demand-Side Macro Shock Analysis Skill

This skill builds an Excel workbook that analyzes the GDP impact of a large
investment spending shock on a small open economy using the demand-side
macro accounting framework.

## Workflow

1. **Data Collection**: Fetch IMF WEO data (real GDP growth, nominal GDP) and
   download Supply-Use Tables from the country statistics office (geostat.ge
   for Georgia). Also download GDP data files from geostat.

2. **WEO_Data Sheet**: Populate with real GDP growth rates, nominal GDP,
   real GDP, GDP deflator index, and deflator growth. Extend projections
   using the 2027 growth rate as fixed anchor and average recent-4-year
   deflator growth.

3. **SUT Sheets**: Copy SUPPLY and USE (38-38) sheets from the downloaded
   SUT file into the workbook.

4. **SUT Calc Sheet**: Link construction-industry data from the SUT sheets
   to calculate the estimated import content share for construction.

5. **NA Sheet**: Build three scenario tables:
   - Scenario 1: Demand multiplier = 0.8 (small open economy default)
   - Scenario 2: Demand multiplier = 1.0
   - Scenario 3: Import content share = 0.5

   Each scenario uses bell-shaped project allocation over 8 years,
   converts USD investment to GEL, and calculates GDP impact with formulas.

## Entry Point

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-demand-shock/scripts')
from utils import build_complete_workbook, validate_workbook

# Build the complete workbook
output_path = '/root/test_demand.xlsx'
build_complete_workbook(output_path)

# Validate
validate_workbook(output_path)
```

## Key Functions

- `fetch_imf_weo_data(country_code)` - Fetch WEO indicators from IMF API
- `download_sut_file(url, output_path)` - Download SUT Excel file
- `download_geostat_gdp_files(output_dir)` - Download GDP data from geostat.ge
- `extract_geostat_annual_gdp(file, label)` - Extract annual GDP values
- `find_latest_sut_url()` - Find latest SUT file URL on geostat.ge
- `copy_sut_sheet(src_wb, src_name, tgt_wb, tgt_name)` - Copy sheet between workbooks
- `build_weo_data_sheet(wb, weo_data, geostat_data)` - Build WEO_Data sheet
- `build_sut_calc_sheet(wb, supply_name, use_name)` - Build SUT Calc sheet
- `build_na_sheet(wb, ...)` - Build NA scenario table
- `build_complete_workbook(output_path, ...)` - End-to-end orchestration
- `validate_workbook(path)` - Check workbook structure and completeness
- `bell_shape_allocation(n_years)` - Generate bell-shaped allocation profile
