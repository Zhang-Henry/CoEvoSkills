"""
PID controller gain tuning using IMC (Internal Model Control) method.
For a first-order system: G(s) = K / (tau*s + 1)
IMC tuning with filter constant lambda gives:
  Kp = tau / (K * lambda)
  Ki = Kp / tau = 1 / (K * lambda)
  Kd = 0 (for first-order systems)
"""
import json


def compute_gains(K, tau, lambda_factor=None):
    """
    Compute PID gains using IMC tuning.
    
    Args:
        K: process gain (C per % power)
        tau: time constant (seconds)
        lambda_factor: closed-loop time constant. If None, uses tau/2 for moderate response.
    
    Returns:
        dict with Kp, Ki, Kd, lambda
    """
    if lambda_factor is None:
        # Choose lambda for good balance of speed and stability
        # Smaller lambda = faster but more aggressive
        # For settling time < 120s, we need reasonably fast response
        lambda_factor = max(tau * 0.5, 5.0)
    
    # IMC tuning for first-order system
    Kp = tau / (K * lambda_factor)
    Ki = Kp / tau  # = 1 / (K * lambda_factor)
    Kd = 0.0
    
    gains = {
        "Kp": round(float(Kp), 4),
        "Ki": round(float(Ki), 4),
        "Kd": round(float(Kd), 4),
        "lambda": round(float(lambda_factor), 4)
    }
    
    return gains


def save_tuned_gains(gains, path="/root/tuned_gains.json"):
    """Save tuned gains to JSON file."""
    with open(path, 'w') as f:
        json.dump(gains, f, indent=2)
    return path
