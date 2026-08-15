---
name: evo-r2r-mpc
description: "MPC controller for 6-section Roll-to-Roll web handling system. Derives linearized state-space model using Euler discretization matching the simulator, designs MPC with LQR fallback, runs simulation with time-varying reference tracking, and computes performance metrics."
---

# R2R MPC Controller Skill

## Overview
Implements Model Predictive Control for a 6-section Roll-to-Roll manufacturing line.
Handles tension reference step changes while maintaining stability.

## Key Insights
- The simulator uses **Euler integration**, so discretization must use `A_d = I + A_c*dt`, `B_d = B_c*dt`
- Matrix exponential discretization gives different dynamics and worse prediction accuracy
- The simulator uses `v_inlet = x_ref[6, t_idx]` (v1_ref) as inlet velocity, which differs from config v0
- The theoretical reference (computed with v0) is NOT a true equilibrium of the simulator
- The controller handles this bias through feedback

## Components
- `linearize.py`: Analytical Jacobians, Euler discretization, simulator equilibrium finder
- `mpc_controller.py`: Condensed QP MPC with time-varying reference tracking, LQR fallback
- `simulate.py`: Closed-loop simulation with R2RSimulator
- `metrics.py`: SSE, settling time, max/min tension computation
- `run_all.py`: End-to-end entry point

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-r2r-mpc/scripts')

from linearize import get_linearized_system, load_config
from mpc_controller import MPCController, compute_lqr_gain
from simulate import run_simulation, save_control_log
from metrics import compute_metrics, save_metrics
import numpy as np
import json

# Linearize
cfg = load_config("/root/system_config.json")
n = cfg["num_sections"]
A_d, B_d, A_c, B_c, x_ref, u_ref = get_linearized_system(use_final=False)

# Design controller
horizon_N = 10
Q_diag = [100.0]*n + [0.1]*n
R_diag = [0.05]*n
K_lqr, _ = compute_lqr_gain(A_d, B_d, np.diag(Q_diag), np.diag(R_diag))
controller = MPCController(A_d, B_d, Q_diag, R_diag, horizon_N, K_lqr)

# Save params
with open('/root/controller_params.json', 'w') as f:
    json.dump({
        "horizon_N": horizon_N, "Q_diag": Q_diag, "R_diag": R_diag,
        "K_lqr": K_lqr.tolist(), "A_matrix": A_d.tolist(), "B_matrix": B_d.tolist()
    }, f, indent=2)

# Simulate
sys.path.insert(0, '/root')
from r2r_simulator import R2RSimulator
sim = R2RSimulator()
log_data = run_simulation(sim, controller, total_time=6.0, use_mpc=True, use_tracking=True)
save_control_log(log_data, '/root/control_log.json')

# Metrics
metrics = compute_metrics(log_data)
save_metrics(metrics, '/root/metrics.json')
```

## Dynamics
State: x = [T1..T6, v1..v6] (12 states)
Input: u = [u1..u6] (6 motor torques)

- dT_i/dt = (EA/L)*(v_i - v_{i-1}) + (1/L)*(v_{i-1}*T_{i-1} - v_i*T_i)
- dv_i/dt = (R^2/J)*(T_{i+1} - T_i) + (R/J)*u_i - (fb/J)*v_i

## Performance Targets
- Steady-state error < 2.0N
- Settling time < 4.0s
- Max tension < 50N
- Min tension > 5N
