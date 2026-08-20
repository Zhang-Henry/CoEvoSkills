---
name: evo-hvac-controller
description: "HVAC PID temperature controller skill. Runs calibration, estimates first-order system parameters, tunes PID gains via IMC, executes closed-loop control, and computes performance metrics. Use for thermal control tasks with first-order plant dynamics."
---

# HVAC Temperature Controller Skill

## Overview
This skill implements a complete HVAC temperature control pipeline:
1. **Calibration**: Open-loop step test to characterize the thermal system
2. **Estimation**: Fit first-order model parameters (K, tau) via curve fitting
3. **Tuning**: Compute PID gains using IMC (Internal Model Control) method
4. **Control**: Run closed-loop PID control with anti-windup
5. **Metrics**: Compute rise time, overshoot, settling time, steady-state error, max temp

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-hvac-controller/scripts')
from orchestrator import run_full_pipeline, validate_outputs

# Run the complete pipeline
results = run_full_pipeline(
    output_dir="/root",
    calibration_power=50.0,
    calibration_duration=60.0,
    control_duration=180.0
)

# Validate all outputs
validate_outputs("/root")
```

## Scripts

### scripts/calibration.py
- `run_calibration(sim, heater_power, duration)` - Run open-loop calibration
- `save_calibration_log(log, path)` - Save calibration data to JSON

### scripts/estimation.py
- `estimate_params(calibration_log, ambient_temp)` - Fit K and tau from data
- `save_estimated_params(params, path)` - Save parameters to JSON

### scripts/tuning.py
- `compute_gains(K, tau, lambda_factor)` - Compute PID gains via IMC
- `save_tuned_gains(gains, path)` - Save gains to JSON

### scripts/controller.py
- `PIDController` class with anti-windup
- `run_closed_loop(sim, gains, duration)` - Run PID control loop
- `save_control_log(log, path)` - Save control log to JSON

### scripts/metrics.py
- `compute_metrics(control_log)` - Compute performance metrics
- `save_metrics(metrics, path)` - Save metrics to JSON

### scripts/orchestrator.py
- `run_full_pipeline(output_dir, ...)` - End-to-end entry point
- `validate_outputs(output_dir)` - Validate all output files

## Design Decisions
- IMC tuning with lambda = max(tau/2, 5) for balanced speed/stability
- Anti-windup via back-calculation in PID controller
- Settling band of +/- 0.5C (matching the steady-state error target)
- Overshoot computed as (max_temp - setpoint) / (setpoint - T0)
- Steady-state error averaged over last 20% of data
