#!/usr/bin/env python3
"""Final MPC implementation with time-varying reference tracking."""
import sys, json
import numpy as np
from scipy.linalg import solve_discrete_are

sys.path.insert(0, '/root')
from r2r_simulator import R2RSimulator

with open('/root/system_config.json') as f:
    cfg = json.load(f)

EA=cfg["EA"]; J=cfg["J"]; R_param=cfg["R"]; fb=cfg["fb"]; L=cfg["L"]
v0=cfg["v0"]; dt=cfg["dt"]; n=cfg["num_sections"]
step_time=cfg["step_time"]
T_ref_init=np.array(cfg["T_ref_initial"],dtype=float)
T_ref_final=np.array(cfg["T_ref_final"],dtype=float)

# === Step 1: Linearize ===
def compute_v_ref(T_ref):
    v=np.zeros(n); vp,Tp=v0,0.0
    for i in range(n): v[i]=(EA-Tp)/(EA-T_ref[i])*vp; vp,Tp=v[i],T_ref[i]
    return v

v_ref=compute_v_ref(T_ref_init)
x_ref=np.concatenate([T_ref_init,v_ref])

A_c=np.zeros((12,12)); B_c=np.zeros((12,6))
for i in range(n):
    vim1=v0 if i==0 else v_ref[i-1]; Tim1=0.0 if i==0 else T_ref_init[i-1]
    if i>0: A_c[i,i-1]=vim1/L
    A_c[i,i]=-v_ref[i]/L
    if i>0: A_c[i,n+i-1]=(-EA+Tim1)/L
    A_c[i,n+i]=(EA-T_ref_init[i])/L
for i in range(n):
    A_c[n+i,i]=-R_param**2/J
    if i<n-1: A_c[n+i,i+1]=R_param**2/J
    A_c[n+i,n+i]=-fb/J; B_c[n+i,i]=R_param/J

# Euler discretization (matches simulator's integration)
A_d=np.eye(12)+A_c*dt; B_d=B_c*dt

# === Step 2: Design MPC ===
horizon_N=10
Q_diag=[100.0]*n+[0.1]*n
R_diag=[0.05]*n
Q=np.diag(Q_diag); R_mat=np.diag(R_diag)

# LQR gain (for reporting and terminal cost)
P=solve_discrete_are(A_d,B_d,Q,R_mat)
K_lqr=np.linalg.inv(R_mat+B_d.T@P@B_d)@(B_d.T@P@A_d)

# MPC prediction matrices
nx=12; nu=6; N=horizon_N
Phi=np.zeros((N*nx,nx)); Gamma=np.zeros((N*nx,N*nu))
Apow=np.eye(nx)
for k in range(N):
    Apow=Apow@A_d; Phi[k*nx:(k+1)*nx,:]=Apow
    for j in range(k+1):
        Gamma[k*nx:(k+1)*nx,j*nu:(j+1)*nu]=np.linalg.matrix_power(A_d,k-j)@B_d
Q_bar=np.kron(np.eye(N),Q); R_bar=np.kron(np.eye(N),R_mat)
H=Gamma.T@Q_bar@Gamma+R_bar
H_inv=np.linalg.inv(H)

print(f"K_lqr norm: {np.linalg.norm(K_lqr):.2f}")

# Save params
with open('/root/controller_params.json','w') as f:
    json.dump({
        "horizon_N":horizon_N,
        "Q_diag":Q_diag,
        "R_diag":R_diag,
        "K_lqr":K_lqr.tolist(),
        "A_matrix":A_d.tolist(),
        "B_matrix":B_d.tolist()
    },f,indent=2)

# === Step 3: Run simulation ===
sim=R2RSimulator()
x=sim.reset()
log_data=[]

for step in range(int(6.0/dt)):
    x_ref_t,u_ref_t=sim.get_reference()
    
    # Build time-varying reference trajectory across horizon
    X_ref=np.zeros(N*nx); U_ref=np.zeros(N*nu)
    for k in range(N):
        xr,ur=sim.get_reference(sim.t_idx+k)
        X_ref[k*nx:(k+1)*nx]=xr
        U_ref[k*nu:(k+1)*nu]=ur
    
    # Solve MPC QP
    e0=Phi@x+Gamma@U_ref-X_ref
    g=Gamma.T@Q_bar@e0
    dU=-H_inv@g
    u=dU[:nu]+u_ref_t
    
    x=sim.step(u)
    
    log_data.append({
        "time":round(sim.get_time(),4),
        "tensions":x[:6].tolist(),
        "velocities":x[6:].tolist(),
        "control_inputs":u.tolist(),
        "references":x_ref_t.tolist()
    })

with open('/root/control_log.json','w') as f:
    json.dump({"phase":"control","data":log_data},f,indent=2)
print(f"Logged {len(log_data)} entries")

# === Step 4: Metrics ===
times=np.array([d['time'] for d in log_data])
tensions=np.array([d['tensions'] for d in log_data])
controls=np.array([d['control_inputs'] for d in log_data])

last_1s=times>=(times[-1]-1.0)
sse=float(np.mean(np.abs(tensions[last_1s]-T_ref_final)))
max_t=float(np.max(tensions)); min_t=float(np.min(tensions))

post_step=np.where(times>=step_time)[0]
settling=float(times[-1]-step_time)
for idx in post_step:
    if np.all(np.abs(tensions[idx:]-T_ref_final)<2.0):
        settling=float(times[idx]-step_time); break

metrics={"steady_state_error":round(sse,4),"settling_time":round(settling,4),
         "max_tension":round(max_t,4),"min_tension":round(min_t,4)}
with open('/root/metrics.json','w') as f:
    json.dump(metrics,f,indent=2)

print(f"Metrics: {json.dumps(metrics)}")
print(f"All pass: {sse<2 and settling<4 and max_t<50 and min_t>5}")
print(f"u range: [{np.min(controls):.1f}, {np.max(controls):.1f}]")

# Verify K_lqr consistency
K_check=np.linalg.inv(R_mat+B_d.T@P@B_d)@(B_d.T@P@A_d)
print(f"K consistent: {np.allclose(K_lqr,K_check)}")

# Check trajectory
for t in [0.01,0.49,0.50,0.51,0.55,1.0,3.0,6.0]:
    idx=np.argmin(np.abs(times-t))
    print(f"  t={times[idx]:.2f}: T3={tensions[idx,2]:.2f} max_err={np.max(np.abs(tensions[idx]-T_ref_final)):.2f}")
