"""
End-to-end orchestrator for HVAC temperature control task.
Runs calibration, estimation, tuning, control, and metrics computation.
"""
import sys
import json

sys.path.insert(0, '/root')

from calibration import run_calibration, save_calibration_log
from estimation import estimate_params, save_estimated_params
from tuning import compute_gains, save_tuned_gains
from controller import run_closed_loop, save_control_log
from metrics import compute_metrics, save_metrics


def run_full_pipeline(output_dir="/root", calibration_power=50.0, calibration_duration=60.0, control_duration=180.0):
    """
    Run the complete HVAC control pipeline.
    
    Args:
        output_dir: directory for output files
        calibration_power: heater power for calibration test
        calibration_duration: duration of calibration in seconds
        control_duration: duration of closed-loop control in seconds
    
    Returns:
        dict with all results
    """
    from hvac_simulator import HVACSimulator
    
    sim = HVACSimulator()
    
    # Step 1: Calibration
    print("=== Step 1: Calibration ===")
    cal_log = run_calibration(sim, heater_power=calibration_power, duration=calibration_duration)
    save_calibration_log(cal_log, f"{output_dir}/calibration_log.json")
    print(f"Calibration: {len(cal_log['data'])} data points over {cal_log['data'][-1]['time']}s")
    
    # Step 2: Parameter Estimation
    print("\n=== Step 2: Parameter Estimation ===")
    ambient = sim.get_ambient_temp()
    params = estimate_params(cal_log, ambient_temp=ambient)
    save_estimated_params(params, f"{output_dir}/estimated_params.json")
    print(f"Estimated K={params['K']}, tau={params['tau']}, R²={params['r_squared']}")
    
    # Step 3: Controller Tuning
    print("\n=== Step 3: Controller Tuning ===")
    gains = compute_gains(params["K"], params["tau"])
    save_tuned_gains(gains, f"{output_dir}/tuned_gains.json")
    print(f"Gains: Kp={gains['Kp']}, Ki={gains['Ki']}, Kd={gains['Kd']}")
    
    # Step 4: Closed-Loop Control
    print("\n=== Step 4: Closed-Loop Control ===")
    ctrl_log = run_closed_loop(sim, gains, duration=control_duration)
    save_control_log(ctrl_log, f"{output_dir}/control_log.json")
    print(f"Control: {len(ctrl_log['data'])} data points over {ctrl_log['data'][-1]['time']}s")
    
    # Step 5: Metrics
    print("\n=== Step 5: Metrics ===")
    met = compute_metrics(ctrl_log)
    save_metrics(met, f"{output_dir}/metrics.json")
    print(f"Rise time: {met['rise_time']}s")
    print(f"Overshoot: {met['overshoot']:.4f} ({met['overshoot']*100:.1f}%)")
    print(f"Settling time: {met['settling_time']}s")
    print(f"Steady-state error: {met['steady_state_error']:.4f}C")
    print(f"Max temp: {met['max_temp']:.4f}C")
    
    # Validate against targets
    print("\n=== Validation ===")
    targets_met = True
    if met['steady_state_error'] >= 0.5:
        print(f"FAIL: steady-state error {met['steady_state_error']} >= 0.5C")
        targets_met = False
    if met['settling_time'] >= 120:
        print(f"FAIL: settling time {met['settling_time']} >= 120s")
        targets_met = False
    if met['overshoot'] >= 0.10:
        print(f"FAIL: overshoot {met['overshoot']*100:.1f}% >= 10%")
        targets_met = False
    if ctrl_log['data'][-1]['time'] < 150:
        print(f"FAIL: control duration {ctrl_log['data'][-1]['time']} < 150s")
        targets_met = False
    if met['max_temp'] >= 30:
        print(f"FAIL: max temp {met['max_temp']} >= 30C")
        targets_met = False
    
    if targets_met:
        print("ALL TARGETS MET!")
    
    return {
        "calibration_log": cal_log,
        "estimated_params": params,
        "tuned_gains": gains,
        "control_log": ctrl_log,
        "metrics": met
    }


def validate_outputs(output_dir="/root"):
    """
    Validate all output files exist and are consistent.
    """
    import os
    required_files = [
        "calibration_log.json",
        "estimated_params.json",
        "tuned_gains.json",
        "control_log.json",
        "metrics.json"
    ]
    
    errors = []
    for fname in required_files:
        fpath = os.path.join(output_dir, fname)
        if not os.path.exists(fpath):
            errors.append(f"Missing: {fpath}")
            continue
        with open(fpath) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            errors.append(f"{fname} is not a JSON object")
    
    # Validate calibration log
    with open(os.path.join(output_dir, "calibration_log.json")) as f:
        cal = json.load(f)
    if len(cal.get("data", [])) < 20:
        errors.append(f"calibration_log has {len(cal.get('data', []))} points, need >= 20")
    if cal["data"][-1]["time"] < 30:
        errors.append(f"calibration duration {cal['data'][-1]['time']}s < 30s required")
    
    # Validate control log
    with open(os.path.join(output_dir, "control_log.json")) as f:
        ctrl = json.load(f)
    if ctrl["data"][-1]["time"] < 150:
        errors.append(f"control duration {ctrl['data'][-1]['time']}s < 150s required")
    
    # Validate metrics
    with open(os.path.join(output_dir, "metrics.json")) as f:
        met = json.load(f)
    required_keys = ["rise_time", "overshoot", "settling_time", "steady_state_error", "max_temp"]
    for k in required_keys:
        if k not in met:
            errors.append(f"metrics.json missing key: {k}")
    
    if errors:
        print("VALIDATION ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return False
    
    print("All output files validated successfully.")
    return True


if __name__ == "__main__":
    run_full_pipeline()
    validate_outputs()
