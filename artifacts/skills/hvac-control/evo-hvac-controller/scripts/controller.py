#!/usr/bin/env python3
"""Closed-loop PID controller for HVAC system."""
import sys
import json
import numpy as np

def run_control(simulator_path="/root", gains_path="/root/tuned_gains.json",
                control_log_path="/root/control_log.json",
                metrics_path="/root/metrics.json",
                duration=200.0, setpoint=22.0):
    """Run closed-loop PID control.
    
    Args:
        simulator_path: directory containing hvac_simulator.py
        gains_path: path to tuned_gains.json
        control_log_path: where to write control_log.json
        metrics_path: where to write metrics.json
        duration: control duration in seconds
        setpoint: target temperature
    
    Returns:
        tuple of (control_log dict, metrics dict)
    """
    sys.path.insert(0, simulator_path)
    from hvac_simulator import HVACSimulator
    
    with open(gains_path, 'r') as f:
        gains = json.load(f)
    
    Kp = gains["Kp"]
    Ki = gains["Ki"]
    Kd = gains["Kd"]
    
    sim = HVACSimulator()
    initial_temp = sim.reset()
    dt = sim.get_dt()
    
    # PID state
    integral = 0.0
    prev_error = setpoint - initial_temp
    
    # Anti-windup limits
    integral_max = 100.0 / max(Ki, 1e-6)  # prevent windup
    
    data = []
    steps = int(duration / dt)
    
    for i in range(steps):
        # Current measurement (from last step or initial)
        if i == 0:
            current_temp = initial_temp
        else:
            current_temp = data[-1]["temperature"]
        
        error = setpoint - current_temp
        
        # PID calculation
        # Proportional
        P = Kp * error
        
        # Integral with anti-windup
        integral += error * dt
        integral = np.clip(integral, -integral_max, integral_max)
        I = Ki * integral
        
        # Derivative (on error)
        derivative = (error - prev_error) / dt
        D = Kd * derivative
        prev_error = error
        
        # Total control output
        output = P + I + D
        
        # Clamp to actuator range
        output_clamped = np.clip(output, 0.0, 100.0)
        
        # Anti-windup: if saturated, don't accumulate integral
        if output != output_clamped:
            integral -= error * dt  # undo last integration
        
        # Step simulator
        result = sim.step(float(output_clamped))
        
        data.append({
            "time": result["time"],
            "temperature": result["temperature"],
            "setpoint": setpoint,
            "heater_power": result["heater_power"],
            "error": round(setpoint - result["temperature"], 4)
        })
    
    control_log = {
        "phase": "control",
        "setpoint": setpoint,
        "data": data
    }
    
    with open(control_log_path, 'w') as f:
        json.dump(control_log, f, indent=2)
    
    # Calculate metrics
    metrics = compute_metrics(data, setpoint)
    
    with open(metrics_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    
    print(f"Control complete: {len(data)} steps over {data[-1]['time']}s")
    print(f"Metrics: {json.dumps(metrics, indent=2)}")
    return control_log, metrics


def compute_metrics(data, setpoint):
    """Compute control performance metrics from data.
    
    Args:
        data: list of dicts with time, temperature, setpoint
        setpoint: target temperature
    
    Returns:
        dict with rise_time, overshoot, settling_time, steady_state_error, max_temp
    """
    times = np.array([d["time"] for d in data])
    temps = np.array([d["temperature"] for d in data])
    
    initial_temp = temps[0]
    temp_range = setpoint - initial_temp  # expected rise
    
    # Rise time: time to first reach setpoint (or 90% of the way)
    rise_threshold = initial_temp + 0.9 * temp_range
    rise_time = None
    for i, t in enumerate(temps):
        if t >= rise_threshold:
            rise_time = times[i]
            break
    if rise_time is None:
        rise_time = times[-1]
    
    # Max temperature
    max_temp = float(np.max(temps))
    
    # Overshoot: (max_temp - setpoint) / (setpoint - initial_temp)
    if max_temp > setpoint:
        overshoot = (max_temp - setpoint) / temp_range if temp_range > 0 else 0.0
    else:
        overshoot = 0.0
    
    # Settling time: last time the temperature leaves the ±0.5C band around setpoint
    settling_band = 0.5
    settling_time = times[-1]  # default to end
    # Find the last time it was outside the band
    for i in range(len(temps) - 1, -1, -1):
        if abs(temps[i] - setpoint) > settling_band:
            if i < len(temps) - 1:
                settling_time = times[i + 1]
            else:
                settling_time = times[-1]
            break
    else:
        settling_time = times[0]  # always within band (unlikely)
    
    # Steady-state error: average error over last 20% of data
    last_portion = int(len(temps) * 0.2)
    if last_portion < 1:
        last_portion = 1
    ss_error = abs(float(np.mean(temps[-last_portion:]) - setpoint))
    
    metrics = {
        "rise_time": round(float(rise_time), 2),
        "overshoot": round(float(overshoot), 4),
        "settling_time": round(float(settling_time), 2),
        "steady_state_error": round(float(ss_error), 4),
        "max_temp": round(float(max_temp), 4)
    }
    
    return metrics

if __name__ == "__main__":
    run_control()
