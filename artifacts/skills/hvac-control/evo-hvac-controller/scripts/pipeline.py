#!/usr/bin/env python3
"""End-to-end pipeline: calibrate, estimate, tune, control."""
import sys
import os

def run_pipeline(simulator_path="/root", output_dir="/root",
                 cal_power=50.0, cal_duration=60.0,
                 control_duration=200.0, setpoint=22.0):
    """Run the complete HVAC control pipeline.
    
    Args:
        simulator_path: directory containing hvac_simulator.py
        output_dir: directory for all output JSON files
        cal_power: heater power for calibration test
        cal_duration: calibration duration in seconds
        control_duration: control run duration in seconds
        setpoint: target temperature
    """
    # Add scripts directory to path
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, scripts_dir)
    
    from calibration import run_calibration
    from estimation import estimate_parameters
    from tuning import calculate_gains
    from controller import run_control
    
    cal_path = os.path.join(output_dir, "calibration_log.json")
    params_path = os.path.join(output_dir, "estimated_params.json")
    gains_path = os.path.join(output_dir, "tuned_gains.json")
    control_path = os.path.join(output_dir, "control_log.json")
    metrics_path = os.path.join(output_dir, "metrics.json")
    
    print("=" * 60)
    print("STEP 1: Calibration")
    print("=" * 60)
    run_calibration(simulator_path, cal_path, cal_power, cal_duration)
    
    print("\n" + "=" * 60)
    print("STEP 2: Parameter Estimation")
    print("=" * 60)
    params = estimate_parameters(cal_path, params_path)
    
    print("\n" + "=" * 60)
    print("STEP 3: Gain Tuning")
    print("=" * 60)
    calculate_gains(params_path, gains_path)
    
    print("\n" + "=" * 60)
    print("STEP 4: Closed-Loop Control")
    print("=" * 60)
    run_control(simulator_path, gains_path, control_path, metrics_path,
                control_duration, setpoint)
    
    print("\n" + "=" * 60)
    print("Pipeline complete! All output files written to:", output_dir)
    print("=" * 60)

if __name__ == "__main__":
    run_pipeline()
