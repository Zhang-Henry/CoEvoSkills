import numpy as np
import pandas as pd
import netCDF4 as nc
import subprocess
import os
import re
import shutil


def update_nml_param(nml_file, param_name, new_value):
    """Update a single parameter in a GLM namelist file."""
    with open(nml_file, 'r') as f:
        content = f.read()
    pattern = rf'(\s*{param_name}\s*=\s*)([^\n,!]+)'
    match = re.search(pattern, content)
    if match:
        content = content[:match.start(2)] + str(new_value) + content[match.end(2):]
    with open(nml_file, 'w') as f:
        f.write(content)


def run_glm(working_dir, output_dir=None):
    """Run GLM in the specified working directory. Returns True if successful."""
    if output_dir is None:
        output_dir = os.path.join(working_dir, 'output')
    # Clean output directory
    os.makedirs(output_dir, exist_ok=True)
    for f in os.listdir(output_dir):
        fpath = os.path.join(output_dir, f)
        if os.path.isfile(fpath):
            os.remove(fpath)
    result = subprocess.run(['glm'], cwd=working_dir, capture_output=True, text=True, timeout=120)
    output_nc = os.path.join(output_dir, 'output.nc')
    return os.path.exists(output_nc)


def calc_rmse(output_nc_path, obs_csv_path):
    """Calculate RMSE between GLM output and field observations.
    
    Args:
        output_nc_path: Path to GLM output.nc file
        obs_csv_path: Path to CSV with columns: datetime, depth, temp
    
    Returns:
        float: RMSE in degrees Celsius
    """
    obs = pd.read_csv(obs_csv_path)
    obs['datetime'] = pd.to_datetime(obs['datetime'])
    
    ds = nc.Dataset(output_nc_path)
    time_var = ds.variables['time']
    times = nc.num2date(time_var[:], time_var.units)
    sim_dates = pd.to_datetime([str(t) for t in times])
    
    temp_all = ds.variables['temp'][:, :, 0, 0]
    z_all = ds.variables['z'][:, :, 0, 0]
    ns_all = ds.variables['NS'][:]
    
    errors = []
    for idx, row in obs.iterrows():
        obs_dt = row['datetime']
        obs_depth = row['depth']
        obs_temp = row['temp']
        if pd.isna(obs_temp):
            continue
        time_diffs = np.abs((sim_dates - obs_dt).total_seconds())
        closest_idx = np.argmin(time_diffs)
        if time_diffs[closest_idx] > 86400:
            continue
        ns = int(ns_all[closest_idx])
        if ns < 2:
            continue
        z_profile = z_all[closest_idx, :ns]
        t_profile = temp_all[closest_idx, :ns]
        surface_height = z_profile[-1]
        target_height = surface_height - obs_depth
        if target_height < z_profile[0]:
            sim_temp = t_profile[0]
        elif target_height > z_profile[-1]:
            sim_temp = t_profile[-1]
        else:
            sim_temp = np.interp(target_height, z_profile, t_profile)
        errors.append((sim_temp - obs_temp) ** 2)
    
    ds.close()
    return np.sqrt(np.mean(errors))


def calibrate_glm(working_dir, obs_csv_path, param_trials, nml_file='glm3.nml'):
    """Run a grid search over parameter trials to minimize RMSE.
    
    Args:
        working_dir: Directory containing glm3.nml and bcs/
        obs_csv_path: Path to observation CSV
        param_trials: List of dicts, each mapping param_name -> value
        nml_file: Name of the namelist file
    
    Returns:
        tuple: (best_rmse, best_params)
    """
    nml_path = os.path.join(working_dir, nml_file)
    output_nc = os.path.join(working_dir, 'output', 'output.nc')
    
    # Save original
    shutil.copy(nml_path, nml_path + '.orig')
    
    best_rmse = float('inf')
    best_params = {}
    
    # First get baseline
    if run_glm(working_dir):
        best_rmse = calc_rmse(output_nc, obs_csv_path)
        print(f"Baseline RMSE: {best_rmse:.4f}")
    
    for trial in param_trials:
        # Reset to original
        shutil.copy(nml_path + '.orig', nml_path)
        
        # Apply trial parameters
        for param, value in trial.items():
            update_nml_param(nml_path, param, value)
        
        print(f"Trying: {trial}")
        
        if run_glm(working_dir):
            rmse = calc_rmse(output_nc, obs_csv_path)
            print(f"  RMSE: {rmse:.4f}")
            if rmse < best_rmse:
                best_rmse = rmse
                best_params = trial.copy()
                shutil.copy(nml_path, nml_path + '.best')
                print(f"  *** New best! ***")
        else:
            print(f"  GLM failed")
    
    # Apply best parameters
    if best_params:
        shutil.copy(nml_path + '.best', nml_path)
    else:
        shutil.copy(nml_path + '.orig', nml_path)
    
    # Final run with best params
    run_glm(working_dir)
    final_rmse = calc_rmse(output_nc, obs_csv_path)
    print(f"\nFinal RMSE: {final_rmse:.4f}")
    
    # Cleanup temp files
    for ext in ['.orig', '.best']:
        tmp = nml_path + ext
        if os.path.exists(tmp):
            os.remove(tmp)
    
    return final_rmse, best_params


def run_end_to_end(working_dir, obs_csv_path, output_nc_path=None, target_rmse=2.0):
    """End-to-end entry point: run GLM, check RMSE, calibrate if needed.
    
    Args:
        working_dir: Directory containing glm3.nml and bcs/
        obs_csv_path: Path to observation CSV
        output_nc_path: Expected output path (default: working_dir/output/output.nc)
        target_rmse: Target RMSE threshold in degrees C
    
    Returns:
        float: Final RMSE
    """
    if output_nc_path is None:
        output_nc_path = os.path.join(working_dir, 'output', 'output.nc')
    
    os.makedirs(os.path.join(working_dir, 'output'), exist_ok=True)
    
    # First try with existing config
    print("Running GLM with current config...")
    if not run_glm(working_dir):
        raise RuntimeError("GLM failed to run with initial config")
    
    rmse = calc_rmse(output_nc_path, obs_csv_path)
    print(f"Initial RMSE: {rmse:.4f}")
    
    if rmse < target_rmse:
        print(f"RMSE {rmse:.4f} < {target_rmse}, no calibration needed.")
        return rmse
    
    # Calibration needed - try key parameters
    print(f"\nRMSE {rmse:.4f} >= {target_rmse}, starting calibration...")
    
    # Generate parameter trials for common sensitive parameters
    param_trials = []
    
    # Wind factor variations
    for wf in [0.8, 0.85, 0.9, 0.95, 1.05, 1.1]:
        param_trials.append({'wind_factor': wf})
    
    # Kw variations
    for kw in [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        param_trials.append({'Kw': kw})
    
    # Bulk transfer coefficients
    for cd_val in [0.0010, 0.0012, 0.0015]:
        param_trials.append({'cd': cd_val, 'ce': cd_val, 'ch': cd_val})
    
    # Combined trials with best single-param candidates
    for wf in [0.85, 0.9, 0.95]:
        for kw in [0.30, 0.35, 0.40]:
            param_trials.append({'wind_factor': wf, 'Kw': kw})
    
    final_rmse, best_params = calibrate_glm(
        working_dir, obs_csv_path, param_trials
    )
    
    if final_rmse >= target_rmse:
        print(f"WARNING: Could not achieve target RMSE {target_rmse}. Best: {final_rmse:.4f}")
    
    return final_rmse


def validate_output(output_nc_path, obs_csv_path, target_rmse=2.0):
    """Validate that the output meets requirements.
    
    Args:
        output_nc_path: Path to GLM output.nc
        obs_csv_path: Path to observation CSV
        target_rmse: Maximum acceptable RMSE
    
    Returns:
        bool: True if validation passes
    """
    if not os.path.exists(output_nc_path):
        print(f"FAIL: Output file not found: {output_nc_path}")
        return False
    
    # Check file can be opened and has required variables
    try:
        ds = nc.Dataset(output_nc_path)
        required_vars = ['time', 'temp', 'z', 'NS']
        for v in required_vars:
            if v not in ds.variables:
                print(f"FAIL: Missing variable {v} in output")
                ds.close()
                return False
        
        # Check time range
        time_var = ds.variables['time']
        times = nc.num2date(time_var[:], time_var.units)
        ds.close()
        
        print(f"Output time range: {times[0]} to {times[-1]}")
        print(f"Output timesteps: {len(times)}")
    except Exception as e:
        print(f"FAIL: Error reading output: {e}")
        return False
    
    # Check RMSE
    rmse = calc_rmse(output_nc_path, obs_csv_path)
    print(f"RMSE: {rmse:.4f}")
    
    if rmse >= target_rmse:
        print(f"FAIL: RMSE {rmse:.4f} >= {target_rmse}")
        return False
    
    print(f"PASS: RMSE {rmse:.4f} < {target_rmse}")
    return True
