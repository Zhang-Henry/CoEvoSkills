"""
Calibration module: runs open-loop test to characterize the thermal system.
"""
import json
import sys
sys.path.insert(0, '/root')


def run_calibration(sim, heater_power=50.0, duration=60.0):
    """
    Run open-loop calibration with constant heater power.
    
    Args:
        sim: HVACSimulator instance (already reset)
        heater_power: constant heater power to apply (0-100%)
        duration: how long to run in seconds
    
    Returns:
        dict with calibration log data
    """
    initial_temp = sim.reset()
    dt = sim.get_dt()
    steps = int(duration / dt)
    
    data = [{"time": 0.0, "temperature": round(initial_temp, 4), "heater_power": 0.0}]
    
    for i in range(steps):
        result = sim.step(heater_power)
        data.append({
            "time": result["time"],
            "temperature": result["temperature"],
            "heater_power": result["heater_power"]
        })
    
    calibration_log = {
        "phase": "calibration",
        "heater_power_test": heater_power,
        "data": data
    }
    
    return calibration_log


def save_calibration_log(calibration_log, path="/root/calibration_log.json"):
    """Save calibration log to JSON file."""
    with open(path, 'w') as f:
        json.dump(calibration_log, f, indent=2)
    return path
