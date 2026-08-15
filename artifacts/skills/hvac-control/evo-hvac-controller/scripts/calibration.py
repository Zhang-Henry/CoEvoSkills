#!/usr/bin/env python3
"""Calibration: run open-loop test to characterize the thermal system."""
import sys
import json
import numpy as np

def run_calibration(simulator_path="/root", output_path="/root/calibration_log.json",
                    test_power=50.0, duration=60.0):
    """Run open-loop calibration with specified heater power.
    
    Args:
        simulator_path: directory containing hvac_simulator.py
        output_path: where to write calibration_log.json
        test_power: heater power % to use for calibration
        duration: how long to run in seconds
    
    Returns:
        dict with calibration data
    """
    sys.path.insert(0, simulator_path)
    from hvac_simulator import HVACSimulator
    
    sim = HVACSimulator()
    initial_temp = sim.reset()
    dt = sim.get_dt()
    
    # Collect data: first a few steps at 0 power, then at test_power
    data = [{"time": 0.0, "temperature": round(initial_temp, 4), "heater_power": 0.0}]
    
    # Run with test power for the full duration
    steps = int(duration / dt)
    for i in range(steps):
        result = sim.step(test_power)
        data.append({
            "time": result["time"],
            "temperature": result["temperature"],
            "heater_power": result["heater_power"]
        })
    
    calibration_log = {
        "phase": "calibration",
        "heater_power_test": test_power,
        "data": data
    }
    
    with open(output_path, 'w') as f:
        json.dump(calibration_log, f, indent=2)
    
    print(f"Calibration complete: {len(data)} data points over {data[-1]['time']}s")
    print(f"Initial temp: {data[0]['temperature']:.2f}C, Final temp: {data[-1]['temperature']:.2f}C")
    return calibration_log

if __name__ == "__main__":
    run_calibration()
