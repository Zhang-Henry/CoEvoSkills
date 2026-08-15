---
name: evo-hvac-controller
description: "HVAC temperature controller skill: calibrates a first-order thermal system, estimates K and tau parameters, tunes PID gains via Lambda/IMC method, runs closed-loop control, and computes performance metrics. Use for any first-order thermal system identification and PID control task."
---

# HVAC Temperature Controller Skill

## Overview
This skill implements a complete pipeline for controlling an HVAC system:
1. **Calibration**: Open-loop test to collect thermal response data
2. **Parameter Estimation**: Fit first-order model (K, tau) using curve fitting
3. **Gain Tuning**: Calculate PID gains using Lambda/IMC tuning
4. **Closed-Loop Control**: Run PID controller to reach setpoint
5. **Metrics**: Compute rise time, overshoot, settling time, steady-state error

## Scripts
- `scripts/calibration.py` - Open-loop calibration test
- `scripts/estimation.py` - First-order parameter estimation via scipy curve_fit
- `scripts/tuning.py` - Lambda/IMC PID gain calculation
- `scripts/controller.py` - PID controller with anti-windup
- `scripts/pipeline.py` - End-to-end orchestration

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-hvac-controller/scripts')
from pipeline import run_pipeline

# Run complete pipeline
run_pipeline(
    simulator_path="/root",
    output_dir="/root",
    cal_power=50.0,
    cal_duration=60.0,
    control_duration=200.0,
    setpoint=22.0
)
```

## Output Files
- `calibration_log.json` - Calibration phase data (30+ seconds, 20+ data points)
- `estimated_params.json` - Estimated K, tau, r_squared, fitting_error
- `tuned_gains.json` - PID gains Kp, Ki, Kd, lambda
- `control_log.json` - Control phase data with setpoint tracking
- `metrics.json` - Performance metrics (rise_time, overshoot, settling_time, etc.)

## Performance Targets
- Steady-state error < 0.5C
- Settling time < 120s
- Overshoot < 10%
- Control duration >= 150s
- Max temperature < 30C

## Validation

```python
import json

def validate_outputs(output_dir="/root"):
    """Validate all output files meet requirements."""
    import os
    
    # Check all files exist
    files = ["calibration_log.json", "estimated_params.json", 
             "tuned_gains.json", "control_log.json", "metrics.json"]
    for f in files:
        path = os.path.join(output_dir, f)
        assert os.path.exists(path), f"Missing: {path}"
        with open(path) as fh:
            data = json.load(fh)
        print(f"OK: {f}")
    
    # Validate calibration
    with open(os.path.join(output_dir, "calibration_log.json")) as f:
        cal = json.load(f)
    assert cal["phase"] == "calibration"
    assert len(cal["data"]) >= 20, f"Need 20+ data points, got {len(cal['data'])}"
    duration = cal["data"][-1]["time"] - cal["data"][0]["time"]
    assert duration >= 30, f"Need 30+ seconds, got {duration}"
    
    # Validate metrics
    with open(os.path.join(output_dir, "metrics.json")) as f:
        m = json.load(f)
    assert m["steady_state_error"] < 0.5, f"SSE too high: {m['steady_state_error']}"
    assert m["settling_time"] < 120, f"Settling too slow: {m['settling_time']}"
    assert m["overshoot"] < 0.10, f"Overshoot too high: {m['overshoot']}"
    assert m["max_temp"] < 30.0, f"Max temp too high: {m['max_temp']}"
    
    # Validate control duration
    with open(os.path.join(output_dir, "control_log.json")) as f:
        ctrl = json.load(f)
    ctrl_duration = ctrl["data"][-1]["time"] - ctrl["data"][0]["time"]
    assert ctrl_duration >= 150, f"Control duration too short: {ctrl_duration}"
    
    print("\nAll validations passed!")
    return True

validate_outputs()
```
