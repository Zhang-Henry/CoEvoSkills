"""
Performance metrics computation from control log data.
"""
import json
import numpy as np


def compute_metrics(control_log):
    """
    Compute control performance metrics.
    
    Args:
        control_log: dict with control log data
    
    Returns:
        dict with rise_time, overshoot, settling_time, steady_state_error, max_temp
    """
    data = control_log["data"]
    setpoint = control_log["setpoint"]
    
    times = np.array([d["time"] for d in data])
    temps = np.array([d["temperature"] for d in data])
    
    T0 = temps[0]
    delta_T = setpoint - T0  # expected rise
    
    # Rise time: time to first reach setpoint (or 90% of the way)
    rise_time = None
    for i, t in enumerate(temps):
        if t >= T0 + 0.9 * delta_T:
            rise_time = times[i]
            break
    if rise_time is None:
        rise_time = times[-1]
    
    # Max temperature
    max_temp = float(np.max(temps))
    
    # Overshoot: (max_temp - setpoint) / (setpoint - T0)
    if max_temp > setpoint and delta_T > 0:
        overshoot = (max_temp - setpoint) / delta_T
    else:
        overshoot = 0.0
    
    # Settling time: last time the temperature leaves the +/- 0.5C band around setpoint
    settling_band = 0.5
    settling_time = None
    # Find the last time it goes outside the band
    for i in range(len(temps) - 1, -1, -1):
        if abs(temps[i] - setpoint) > settling_band:
            if i < len(temps) - 1:
                settling_time = times[i + 1]
            else:
                settling_time = times[i]
            break
    if settling_time is None:
        settling_time = times[0]  # was always within band
    
    # Steady-state error: average absolute error over last 20% of data
    last_portion = int(len(temps) * 0.2)
    if last_portion < 1:
        last_portion = 1
    steady_state_error = float(np.mean(np.abs(temps[-last_portion:] - setpoint)))
    
    metrics = {
        "rise_time": round(float(rise_time), 2),
        "overshoot": round(float(overshoot), 4),
        "settling_time": round(float(settling_time), 2),
        "steady_state_error": round(float(steady_state_error), 4),
        "max_temp": round(float(max_temp), 4)
    }
    
    return metrics


def save_metrics(metrics, path="/root/metrics.json"):
    """Save metrics to JSON file."""
    with open(path, 'w') as f:
        json.dump(metrics, f, indent=2)
    return path
