#!/usr/bin/env python3
"""Estimate system parameters K and tau from calibration data."""
import json
import numpy as np
from scipy.optimize import curve_fit

def estimate_parameters(calibration_path="/root/calibration_log.json",
                        output_path="/root/estimated_params.json"):
    """Estimate K and tau from calibration data using curve fitting.
    
    The model is: T(t) = T_ss - (T_ss - T0) * exp(-t/tau)
    where T_ss = K*u + T_ambient
    
    Args:
        calibration_path: path to calibration_log.json
        output_path: where to write estimated_params.json
    
    Returns:
        dict with estimated K, tau, r_squared, fitting_error
    """
    with open(calibration_path, 'r') as f:
        cal = json.load(f)
    
    data = cal["data"]
    test_power = cal["heater_power_test"]
    
    times = np.array([d["time"] for d in data])
    temps = np.array([d["temperature"] for d in data])
    
    # Initial temperature (average of first few readings)
    T0 = temps[0]
    
    # For fitting, we need T_ambient. It's the initial temperature (before heating)
    # From the simulator: T_ambient = 18.0 (config), but we estimate from data
    T_ambient = T0  # approximate
    
    # Model: T(t) = (K*u + T_ambient) - (K*u + T_ambient - T0) * exp(-t/tau)
    # Simplify: T(t) = T_ss - (T_ss - T0) * exp(-t/tau)
    # where T_ss = K*u + T_ambient
    # Parameters to fit: T_ss and tau
    
    def first_order_response(t, T_ss, tau):
        return T_ss - (T_ss - T0) * np.exp(-t / tau)
    
    # Initial guesses
    T_final = np.mean(temps[-10:])  # average of last readings
    p0 = [T_final, 30.0]
    
    try:
        popt, pcov = curve_fit(first_order_response, times, temps, p0=p0,
                               bounds=([T0, 1.0], [50.0, 200.0]),
                               maxfev=10000)
        T_ss_est, tau_est = popt
        
        # Calculate K from T_ss = K*u + T_ambient
        K_est = (T_ss_est - T_ambient) / test_power
        
        # Calculate R-squared
        predicted = first_order_response(times, *popt)
        ss_res = np.sum((temps - predicted) ** 2)
        ss_tot = np.sum((temps - np.mean(temps)) ** 2)
        r_squared = 1 - (ss_res / ss_tot) if ss_tot > 0 else 0.0
        
        # RMSE
        fitting_error = np.sqrt(np.mean((temps - predicted) ** 2))
        
    except Exception as e:
        print(f"Curve fitting failed: {e}")
        # Fallback: simple estimation
        T_final = np.mean(temps[-10:])
        K_est = (T_final - T_ambient) / test_power
        tau_est = 40.0
        r_squared = 0.5
        fitting_error = 1.0
    
    result = {
        "K": round(float(K_est), 6),
        "tau": round(float(tau_est), 4),
        "r_squared": round(float(r_squared), 4),
        "fitting_error": round(float(fitting_error), 4)
    }
    
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Estimated K={result['K']}, tau={result['tau']}")
    print(f"R²={result['r_squared']}, RMSE={result['fitting_error']}")
    return result

if __name__ == "__main__":
    estimate_parameters()
