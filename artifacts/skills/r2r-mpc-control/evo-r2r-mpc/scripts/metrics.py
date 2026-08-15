import numpy as np
import json

def compute_metrics(log_data, config_path="/root/system_config.json"):
    """
    Compute performance metrics from simulation log.
    
    Metrics:
    - steady_state_error: mean absolute error of tensions vs reference in last 1s
    - settling_time: time after step change for all tensions to stay within 2N of final ref
    - max_tension: maximum tension observed across all sections and time
    - min_tension: minimum tension observed across all sections and time
    """
    with open(config_path, 'r') as f:
        cfg = json.load(f)
    
    T_ref_final = np.array(cfg["T_ref_final"])
    step_time = cfg["step_time"]
    
    times = np.array([d["time"] for d in log_data])
    tensions = np.array([d["tensions"] for d in log_data])
    references = np.array([d["references"] for d in log_data])
    
    # Max and min tensions across all time and sections
    max_tension = float(np.max(tensions))
    min_tension = float(np.min(tensions))
    
    # Steady-state error: mean absolute error in the last 1 second
    # compared with the reference tensions from system_config.json
    last_1s_mask = times >= (times[-1] - 1.0)
    if np.sum(last_1s_mask) > 0:
        last_tensions = tensions[last_1s_mask]
        errors = np.abs(last_tensions - T_ref_final)
        steady_state_error = float(np.mean(errors))
    else:
        steady_state_error = float('inf')
    
    # Settling time: time from step change for tensions to enter and stay 
    # within 2N of the final reference
    settling_threshold = 2.0
    post_step_mask = times >= step_time
    post_step_indices = np.where(post_step_mask)[0]
    
    settling_time = float(times[-1] - step_time)  # default: never settled
    
    if len(post_step_indices) > 0:
        for idx in post_step_indices:
            remaining_tensions = tensions[idx:]
            remaining_errors = np.abs(remaining_tensions - T_ref_final)
            if np.all(remaining_errors < settling_threshold):
                settling_time = float(times[idx] - step_time)
                break
    
    metrics = {
        "steady_state_error": round(steady_state_error, 4),
        "settling_time": round(settling_time, 4),
        "max_tension": round(max_tension, 4),
        "min_tension": round(min_tension, 4)
    }
    
    return metrics

def save_metrics(metrics, output_path="/root/metrics.json"):
    """Save metrics to JSON file."""
    with open(output_path, 'w') as f:
        json.dump(metrics, f, indent=2)
    print(f"Metrics saved to {output_path}")
    for k, v in metrics.items():
        print(f"  {k}: {v}")
