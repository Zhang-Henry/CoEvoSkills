import numpy as np
from scipy.linalg import solve_discrete_are

def compute_lqr_gain(A, B, Q, R_mat):
    """Compute discrete-time LQR gain."""
    P = solve_discrete_are(A, B, Q, R_mat)
    K = np.linalg.inv(R_mat + B.T @ P @ B) @ (B.T @ P @ A)
    return K, P

class MPCController:
    """MPC controller using condensed QP (unconstrained)."""
    
    def __init__(self, A, B, Q_diag, R_diag, N, K_lqr=None):
        self.A = A; self.B = B
        self.nx = A.shape[0]; self.nu = B.shape[1]; self.N = N
        self.Q = np.diag(Q_diag); self.R = np.diag(R_diag)
        
        if K_lqr is None:
            self.K_lqr, _ = compute_lqr_gain(A, B, self.Q, self.R)
        else:
            self.K_lqr = np.array(K_lqr)
        
        self._build_matrices()
    
    def _build_matrices(self):
        nx, nu, N = self.nx, self.nu, self.N
        A, B = self.A, self.B
        
        Phi = np.zeros((N*nx, nx))
        Gamma = np.zeros((N*nx, N*nu))
        Apow = np.eye(nx)
        for k in range(N):
            Apow = Apow @ A
            Phi[k*nx:(k+1)*nx, :] = Apow
            for j in range(k+1):
                Gamma[k*nx:(k+1)*nx, j*nu:(j+1)*nu] = np.linalg.matrix_power(A, k-j) @ B
        
        Q_bar = np.kron(np.eye(N), self.Q)
        R_bar = np.kron(np.eye(N), self.R)
        H = Gamma.T @ Q_bar @ Gamma + R_bar
        F = Gamma.T @ Q_bar @ Phi
        
        self.H_inv = np.linalg.inv(H)
        self.K_mpc = self.H_inv[:nu, :] @ F
    
    def compute_control(self, x, x_ref, u_ref):
        """MPC control with constant reference."""
        dx = x - x_ref
        du = -self.K_mpc @ dx
        return du + u_ref
    
    def compute_control_lqr(self, x, x_ref, u_ref):
        """LQR fallback."""
        dx = x - x_ref
        du = -self.K_lqr @ dx
        return du + u_ref
