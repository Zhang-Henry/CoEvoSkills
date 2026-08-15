import numpy as np
import json

def run_simulation(sim, controller, total_time=5.0, use_mpc=True, use_tracking=True):
    """
    Run R2R simulation with MPC controller.
    If use_tracking=True, uses time-varying reference across MPC horizon.
    """
    params = sim.get_params()
    dt = params["dt"]
    n_steps = int(total_time / dt)
    N = controller.N
    
    x = sim.reset()
    log_data = []
    
    for step in range(n_steps):
        x_ref, u_ref = sim.get_reference()
        
        if use_mpc and use_tracking:
            # Build reference trajectory for next N steps
            x_ref_traj = np.zeros((N, controller.nx))
            u_ref_traj = np.zeros((N, controller.nu))
            
            for k in range(N):
                future_idx = sim.t_idx + k
                xr, ur = sim.get_reference(future_idx)
                x_ref_traj[k] = xr
                u_ref_traj[k] = ur
            
            try:
                u = controller.compute_control_tracking(x, x_ref_traj, u_ref_traj)
            except Exception as e:
                u = controller.compute_control(x, x_ref, u_ref)
        elif use_mpc:
            u = controller.compute_control(x, x_ref, u_ref)
        else:
            u = controller.compute_control_lqr(x, x_ref, u_ref)
        
        x = sim.step(u)
        
        entry = {
            "time": round(sim.get_time(), 4),
            "tensions": x[:6].tolist(),
            "velocities": x[6:].tolist(),
            "control_inputs": u.tolist(),
            "references": x_ref.tolist()
        }
        log_data.append(entry)
    
    return log_data

def save_control_log(log_data, output_path="/root/control_log.json"):
    result = {"phase": "control", "data": log_data}
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"Control log saved to {output_path} ({len(log_data)} entries)")
