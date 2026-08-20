"""
System parameter estimation from calibration data.
Fits first-order model: T(t) = T_ss - (T_ss - T0) * exp(-t/tau)
where T_ss = T_ambient + K * u
"""
import json
import numpy as np
from scipy.optimize import curve_fit


def first_order_response(t, T0, K_u, tau):
    """
    First-order step response.
    T(t) = T0 + K_u * (1 - exp(-t/tau))
    where K_u = K * heater_power (the total steady-state rise)
    """
    return T0 + K_u * (1.0 - np.exp(-t / tau))


def estimate_params(calibration_log, ambient_temp=18.0):
    """
    Estimate K and tau from calibration data.
    
    The thermal model is: dT/dt = (1/tau) * (K*u + T_ambient - T)
    At steady state: T_ss = T_ambient + K*u
    Step response from T0: T(t) = T_ss - (T_ss - T0)*exp(-t/tau)
    Which equals: T(t) = T0 + (T_ss - T0)*(1 - exp(-t/tau))
    
    Args:
        calibration_log: dict with calibration data
        ambient_temp: ambient temperature
    
    Returns:
        dict with estimated parameters
    """
    data = calibration_log["data"]
    heater_power = calibration_log["heater_power_test"]
    
    times = np.array([d["time"] for d in data])
    temps = np.array([d["temperature"] for d in data])
    
    T0_measured = temps[0]
    
    # Initial guesses
    T_final = temps[-1]
    K_u_guess = T_final - T0_measured
    tau_guess = 20.0
    
    try:
        popt, pcov = curve_fit(
            first_order_response,
            times, temps,
            p0=[T0_measured, K_u_guess, tau_guess],
            bounds=([T0_measured - 5, 0.01, 1.0], [T0_measured + 5, 50.0, 200.0]),
            maxfev=10000
        )
        T0_fit, K_u_fit, tau_fit = popt
    except Exception as e:
        print(f"Curve fit failed: {e}, using fallback")
        T0_fit = T0_measured
        K_u_fit = K_u_guess if K_u_guess > 0 else 1.0
        tau_fit = tau_guess
    
    # K = K_u / heater_power
    K = K_u_fit / heater_power if heater_power > 0 else 0.1
    
    # Compute R-squared
    T_pred = first_order_response(times, T0_fit, K_u_fit, tau_fit)
    ss_res = np.sum((temps - T_pred) ** 2)
    ss_tot = np.sum((temps - np.mean(temps)) ** 2)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    
    fitting_error = np.sqrt(np.mean((temps - T_pred) ** 2))
    
    params = {
        "K": round(float(K), 6),
        "tau": round(float(tau_fit), 4),
        "r_squared": round(float(r_squared), 6),
        "fitting_error": round(float(fitting_error), 6)
    }
    
    return params


def save_estimated_params(params, path="/root/estimated_params.json"):
    """Save estimated parameters to JSON file."""
    with open(path, 'w') as f:
        json.dump(params, f, indent=2)
    return path
