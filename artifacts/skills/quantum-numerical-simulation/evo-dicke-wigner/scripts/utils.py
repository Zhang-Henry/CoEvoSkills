"""
Utility functions for open Dicke model steady-state Wigner function calculation.
Uses QuTiP PIQS for collective spin operators and Dicke-basis Liouvillian.
"""
import warnings
warnings.filterwarnings('ignore')

import numpy as np
import qutip as qt
from qutip.piqs import Dicke, jspin


def build_spin_hamiltonian(N, omega0):
    """Build spin Hamiltonian H_spin = omega0 * Jz in Dicke basis."""
    jz = jspin(N, 'z')
    return omega0 * jz


def build_spin_liouvillian(N, omega0, dephasing=0.0, pumping=0.0, emission=0.0,
                           collective_pumping=0.0, collective_emission=0.0):
    """
    Build spin-sector Liouvillian using PIQS Dicke class.
    Includes spin Hamiltonian and dissipation.
    """
    h_spin = build_spin_hamiltonian(N, omega0)
    d = Dicke(
        N=N,
        hamiltonian=h_spin,
        dephasing=dephasing,
        pumping=pumping,
        emission=emission,
        collective_pumping=collective_pumping,
        collective_emission=collective_emission,
    )
    return d.liouvillian()


def build_cavity_hamiltonian(omega_c, n_max):
    """Build cavity Hamiltonian H_cav = omega_c * a^dag a."""
    a = qt.destroy(n_max)
    return omega_c * a.dag() * a


def build_cavity_liouvillian(omega_c, n_max, kappa):
    """
    Build cavity-sector Liouvillian: unitary part + cavity loss.
    L_cav = -i[H_cav, .] + kappa * D[a]
    """
    h_cav = build_cavity_hamiltonian(omega_c, n_max)
    a = qt.destroy(n_max)
    # Liouvillian from Hamiltonian
    l_cav = qt.liouvillian(h_cav, [np.sqrt(kappa) * a])
    return l_cav


def build_interaction_superop(N, n_max, g):
    """
    Build interaction superoperator for g*(a + a^dag) x Jx.
    Uses spre and spost: L_int = -i * (spre(H_int) - spost(H_int))
    Following the PIQS convention: H_int = g * (a + a^dag) tensor Jx
    """
    a = qt.destroy(n_max)
    jx = jspin(N, 'x')
    nds = jx.shape[0]  # Dicke space dimension
    
    # Build the interaction Hamiltonian in the full space
    # Cavity is subsystem 0, spin is subsystem 1
    h_int = g * qt.tensor(a + a.dag(), jx)
    
    # Convert to superoperator: -i[H_int, rho] = -i*(H_int*rho - rho*H_int)
    l_int = -1j * (qt.spre(h_int) - qt.spost(h_int))
    return l_int


def build_full_liouvillian(N, omega0, omega_c, g, n_max, kappa,
                           dephasing=0.0, pumping=0.0, emission=0.0,
                           collective_pumping=0.0, collective_emission=0.0):
    """
    Build the full Liouvillian for the open Dicke model.
    L = L_cav (x) I_spin + I_cav (x) L_spin + L_int
    """
    # Spin Liouvillian in Dicke basis
    l_spin = build_spin_liouvillian(
        N, omega0, dephasing=dephasing, pumping=pumping, emission=emission,
        collective_pumping=collective_pumping, collective_emission=collective_emission
    )
    
    # Cavity Liouvillian
    l_cav = build_cavity_liouvillian(omega_c, n_max, kappa)
    
    # Get dimensions
    nds = l_spin.shape[0]  # spin superop dimension
    n_cav_super = l_cav.shape[0]  # cavity superop dimension
    
    # Identity superoperators
    id_spin = qt.to_super(qt.qeye(int(np.sqrt(nds))))
    id_cav = qt.to_super(qt.qeye(n_max))
    
    # Tensor product of Liouvillians
    # L_total = L_cav (x) I_spin + I_cav (x) L_spin + L_int
    l_total = qt.super_tensor(l_cav, id_spin) + qt.super_tensor(id_cav, l_spin)
    
    # Add interaction
    l_int = build_interaction_superop(N, n_max, g)
    l_total = l_total + l_int
    
    return l_total


def find_steady_state(liouvillian, method='direct'):
    """Find the steady state density matrix of the system."""
    rho_ss = qt.steadystate(liouvillian, method=method)
    return rho_ss


def get_cavity_state(rho_ss, n_max, nds):
    """
    Trace out spins to get the cavity reduced density matrix.
    Cavity is subsystem 0.
    """
    # rho_ss is in the full Hilbert space (n_max x nds)
    # ptrace(0) traces out subsystem 1 (spins), keeping subsystem 0 (cavity)
    rho_cav = rho_ss.ptrace(0)
    return rho_cav


def compute_wigner(rho_cav, xvec, yvec):
    """
    Compute the Wigner function of the cavity state on the given grid.
    Returns a 2D array W[i,j] where i indexes p (yvec) and j indexes x (xvec).
    """
    W = qt.wigner(rho_cav, xvec, yvec)
    return W


def save_wigner_csv(W, filepath):
    """Save Wigner function as CSV file."""
    np.savetxt(filepath, W, delimiter=',')


def run_case(case_num, N, omega0, omega_c, g, n_max, kappa,
             dephasing=0.0, pumping=0.0, emission=0.0,
             collective_pumping=0.0, collective_emission=0.0,
             xmin=-6, xmax=6, ngrid=1000, output_dir='/root'):
    """
    Run a single case: build Liouvillian, find steady state,
    trace out spins, compute Wigner function, save to CSV.
    """
    import os
    print(f"Case {case_num}: Building Liouvillian...")
    L = build_full_liouvillian(
        N, omega0, omega_c, g, n_max, kappa,
        dephasing=dephasing, pumping=pumping, emission=emission,
        collective_pumping=collective_pumping, collective_emission=collective_emission
    )
    
    print(f"Case {case_num}: Finding steady state...")
    rho_ss = find_steady_state(L)
    
    # Get Dicke space dimension
    nds = jspin(N, 'z').shape[0]
    
    print(f"Case {case_num}: Tracing out spins...")
    rho_cav = get_cavity_state(rho_ss, n_max, nds)
    
    print(f"Case {case_num}: Computing Wigner function ({ngrid}x{ngrid})...")
    xvec = np.linspace(xmin, xmax, ngrid)
    pvec = np.linspace(xmin, xmax, ngrid)
    W = compute_wigner(rho_cav, xvec, pvec)
    
    filepath = os.path.join(output_dir, f"{case_num}.csv")
    print(f"Case {case_num}: Saving to {filepath}...")
    save_wigner_csv(W, filepath)
    
    # Validation
    print(f"Case {case_num}: W shape={W.shape}, min={W.min():.6f}, max={W.max():.6f}")
    integral = np.trapz(np.trapz(W, pvec, axis=0), xvec)
    print(f"Case {case_num}: Wigner integral ~ {integral:.4f} (should be ~1/pi={1/np.pi:.4f})")
    print(f"Case {case_num}: Done.")
    return W


def run_all_cases(output_dir='/root'):
    """
    Run all 4 cases of the open Dicke model.
    """
    N = 4
    omega0 = 1.0
    omega_c = 1.0
    g = 2.0 / np.sqrt(N)
    kappa = 1.0
    n_max = 16
    
    cases = [
        # Case 1: Local dephasing & local pumping
        dict(case_num=1, dephasing=0.01, pumping=0.1),
        # Case 2: Local dephasing & local emission
        dict(case_num=2, dephasing=0.01, emission=0.1),
        # Case 3: Local dephasing & local emission & collective pumping
        dict(case_num=3, dephasing=0.01, emission=0.1, collective_pumping=0.1),
        # Case 4: Local dephasing & local emission & collective emission
        dict(case_num=4, dephasing=0.01, emission=0.1, collective_emission=0.1),
    ]
    
    for case in cases:
        case_num = case.pop('case_num')
        run_case(
            case_num=case_num,
            N=N, omega0=omega0, omega_c=omega_c, g=g,
            n_max=n_max, kappa=kappa,
            output_dir=output_dir,
            **case
        )


def validate_outputs(output_dir='/root'):
    """Validate all 4 output CSV files."""
    import os
    all_ok = True
    for i in range(1, 5):
        filepath = os.path.join(output_dir, f"{i}.csv")
        if not os.path.exists(filepath):
            print(f"FAIL: {filepath} does not exist")
            all_ok = False
            continue
        W = np.loadtxt(filepath, delimiter=',')
        if W.shape != (1000, 1000):
            print(f"FAIL: {filepath} shape={W.shape}, expected (1000,1000)")
            all_ok = False
        if not np.all(np.isfinite(W)):
            print(f"FAIL: {filepath} contains non-finite values")
            all_ok = False
        # Check normalization
        xvec = np.linspace(-6, 6, 1000)
        integral = np.trapz(np.trapz(W, xvec, axis=0), xvec)
        print(f"Case {i}: shape={W.shape}, integral={integral:.4f}")
        if abs(integral - 1.0/np.pi) > 0.1:
            print(f"WARNING: Case {i} integral deviates from 1/pi={1/np.pi:.4f}")
    if all_ok:
        print("All validations passed.")
    return all_ok
