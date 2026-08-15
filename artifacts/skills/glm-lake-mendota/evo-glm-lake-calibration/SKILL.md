---
name: evo-glm-lake-calibration
description: "Run and calibrate the General Lake Model (GLM) for lake temperature simulation. Use when task requires running GLM, computing RMSE against observations, and calibrating parameters to meet an RMSE threshold."
---

# GLM Lake Model Calibration Skill

This skill provides utilities for running the General Lake Model (GLM),
calculating RMSE against field observations, and calibrating key parameters
to achieve a target RMSE.

## Key Concepts

- GLM uses a namelist config file (glm3.nml) with sections for setup, mixing,
  meteorology, morphometry, inflows, outflows, etc.
- Output is a NetCDF file with variables: temp, z (height from bottom), NS
  (number of active layers), time
- Observations are depth-from-surface; GLM z is height-from-bottom. Convert
  using: target_height = surface_height - obs_depth
- Key calibration parameters: wind_factor, Kw, cd/ce/ch, coef_mix_* coefficients
- wind_factor < 1.0 often reduces RMSE for over-mixed lakes

## Functions

- `update_nml_param(nml_file, param_name, new_value)` - Update a parameter in GLM namelist
- `run_glm(working_dir)` - Run GLM, returns True if successful
- `calc_rmse(output_nc_path, obs_csv_path)` - Calculate RMSE between simulation and observations
- `calibrate_glm(working_dir, obs_csv_path, param_trials)` - Grid search calibration
- `run_end_to_end(working_dir, obs_csv_path, target_rmse=2.0)` - Full pipeline
- `validate_output(output_nc_path, obs_csv_path, target_rmse=2.0)` - Validate results

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-glm-lake-calibration/scripts')
from utils import run_end_to_end, validate_output

# Run end-to-end: GLM execution + calibration if needed
working_dir = '/root'
obs_csv = '/root/field_temp_oxy.csv'
output_nc = '/root/output/output.nc'

final_rmse = run_end_to_end(working_dir, obs_csv, output_nc, target_rmse=2.0)
print(f"Final RMSE: {final_rmse:.4f}")

# Validate
assert validate_output(output_nc, obs_csv, target_rmse=2.0)
```
