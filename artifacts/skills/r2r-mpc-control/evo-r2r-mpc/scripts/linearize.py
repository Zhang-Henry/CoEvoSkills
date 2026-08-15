import numpy as np
import json
from scipy.linalg import expm

def load_config(config_path="/root/system_config.json"):
    with open(config_path, 'r') as f:
        return json.load(f)

def compute_steady_state_velocities(T_ref, EA, L, v0, num_sec):
    v_ref = np.zeros(num_sec)
    v_p, T_p = v0, 0.0
    for i in range(num_sec):
        v_ref[i] = (EA - T_p) / (EA - T_ref[i]) * v_p
        v_p, T_p = v_ref[i], T_ref[i]
    return v_ref

def compute_steady_state_inputs(x_ref, EA, J, R, fb, L, num_sec):
    u_ref = np.zeros(num_sec)
    for i in range(num_sec):
        T_next = x_ref[i+1] if i < num_sec - 1 else 0
        u_ref[i] = fb / R * x_ref[num_sec + i] - R * (T_next - x_ref[i])
    return u_ref

def linearize_continuous(config_path="/root/system_config.json", use_final=False):
    """Compute continuous-time A_c, B_c at reference operating point."""
    cfg = load_config(config_path)
    EA=cfg["EA"]; J=cfg["J"]; R=cfg["R"]; fb=cfg["fb"]; L=cfg["L"]
    v0=cfg["v0"]; n=cfg["num_sections"]
    
    T_ref = np.array(cfg["T_ref_final"] if use_final else cfg["T_ref_initial"], dtype=float)
    v_ref = compute_steady_state_velocities(T_ref, EA, L, v0, n)
    x_ref = np.concatenate([T_ref, v_ref])
    u_ref = compute_steady_state_inputs(x_ref, EA, J, R, fb, L, n)
    
    A_c = np.zeros((2*n, 2*n))
    B_c = np.zeros((2*n, n))
    
    for i in range(n):
        vim1 = v0 if i == 0 else v_ref[i-1]
        Tim1 = 0.0 if i == 0 else T_ref[i-1]
        if i > 0:
            A_c[i, i-1] = (1.0/L) * vim1
        A_c[i, i] = -(1.0/L) * v_ref[i]
        if i > 0:
            A_c[i, n+i-1] = -(EA/L) + (1.0/L) * Tim1
        A_c[i, n+i] = (EA/L) - (1.0/L) * T_ref[i]
    
    for i in range(n):
        A_c[n+i, i] = -(R**2/J)
        if i < n-1:
            A_c[n+i, i+1] = (R**2/J)
        A_c[n+i, n+i] = -(fb/J)
        B_c[n+i, i] = R/J
    
    return A_c, B_c, x_ref, u_ref

def discretize_zoh(A_c, B_c, dt):
    """Exact ZOH discretization using matrix exponential."""
    nx = A_c.shape[0]; nu = B_c.shape[1]
    M = np.zeros((nx+nu, nx+nu))
    M[:nx,:nx] = A_c * dt
    M[:nx,nx:] = B_c * dt
    eM = expm(M)
    return eM[:nx,:nx], eM[:nx,nx:]

def get_linearized_system(config_path="/root/system_config.json", use_final=False):
    """Get discrete-time linearized system."""
    cfg = load_config(config_path)
    A_c, B_c, x_ref, u_ref = linearize_continuous(config_path, use_final)
    A_d, B_d = discretize_zoh(A_c, B_c, cfg["dt"])
    return A_d, B_d, A_c, B_c, x_ref, u_ref
