#!/usr/bin/env python3
"""Calculate PID controller gains from estimated parameters."""
import json

def calculate_gains(params_path="/root/estimated_params.json",
                    output_path="/root/tuned_gains.json",
                    lambda_factor=None):
    """Calculate PID gains using Lambda tuning (IMC-based).
    
    For a first-order system with gain K and time constant tau:
    Lambda tuning gives:
        Kp = tau / (K * lambda)
        Ki = Kp / tau  (or equivalently 1/(K*lambda))
        Kd = 0 (first order, no derivative needed)
    
    where lambda is the desired closed-loop time constant.
    
    Args:
        params_path: path to estimated_params.json
        output_path: where to write tuned_gains.json
        lambda_factor: desired closed-loop time constant (None = auto)
    
    Returns:
        dict with Kp, Ki, Kd, lambda
    """
    with open(params_path, 'r') as f:
        params = json.load(f)
    
    K = params["K"]
    tau = params["tau"]
    
    # Choose lambda for good performance without excessive overshoot
    # lambda ~ tau gives moderate response
    # Smaller lambda = faster but more aggressive
    if lambda_factor is None:
        lambda_factor = tau * 0.8  # slightly aggressive for fast settling
    
    # IMC/Lambda tuning for first-order system
    Kp = tau / (K * lambda_factor)
    Ki = Kp / tau  # integral gain = 1/(K*lambda)
    Kd = 0.0  # no derivative for first-order + noisy measurements
    
    result = {
        "Kp": round(float(Kp), 4),
        "Ki": round(float(Ki), 4),
        "Kd": round(float(Kd), 4),
        "lambda": round(float(lambda_factor), 4)
    }
    
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Tuned gains: Kp={result['Kp']}, Ki={result['Ki']}, Kd={result['Kd']}")
    print(f"Lambda={result['lambda']}")
    return result

if __name__ == "__main__":
    calculate_gains()
