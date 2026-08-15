import numpy as np
import qutip
from qutip import (destroy, tensor, identity, Qobj, spre, spost,
                    operator_to_vector, vector_to_operator, steadystate,
                    wigner)
from qutip.piqs import Dicke, jspin


def build_dicke_system(N, omega0, omegac, g, nmax, loss_params):
    """
    Build the full Liouvillian for the open Dicke model.
    
    Parameters:
    -----------
    N : int - number of two-level systems
    omega0 : float - spin frequency
    omegac : float - cavity frequency  
    g : float - coupling strength
    nmax : int - photon number cutoff (Fock space dimension)
    loss_params : dict with keys:
        'kappa' : cavity loss rate
        'gamma_phi' : local dephasing rate (optional)
        'gamma_up' : local pumping rate (optional)
        'gamma_down' : local emission rate (optional)
        'gamma_UP' : collective pumping rate (optional)
        'gamma_DOWN' : collective emission rate (optional)
    
    Returns:
    --------
    L_total : Qobj - total Liouvillian superoperator
    """
    # --- Spin part using PIQS ---
    # Number of Dicke states for N spins
    nds = qutip.piqs.num_dicke_states(N)
    
    # Build Dicke system for spin Liouvillian
    system = Dicke(N=N)
    
    # Set spin Hamiltonian: omega0 * Jz
    jz_spin = jspin(N, "z")
    jx_spin = jspin(N, "x")
    system.hamiltonian = omega0 * jz_spin
    
    # Set loss rates
    if 'gamma_phi' in loss_params and loss_params['gamma_phi'] > 0:
        system.dephasing = loss_params['gamma_phi']
    if 'gamma_up' in loss_params and loss_params['gamma_up'] > 0:
        system.pumping = loss_params['gamma_up']
    if 'gamma_down' in loss_params and loss_params['gamma_down'] > 0:
        system.emission = loss_params['gamma_down']
    if 'gamma_UP' in loss_params and loss_params['gamma_UP'] > 0:
        system.collective_pumping = loss_params['gamma_UP']
    if 'gamma_DOWN' in loss_params and loss_params['gamma_DOWN'] > 0:
        system.collective_emission = loss_params['gamma_DOWN']
    
    # Build spin Liouvillian (includes spin Hamiltonian)
    L_spin = system.liouvillian()
    
    # --- Cavity part ---
    a = destroy(nmax)
    H_cav = omegac * a.dag() * a
    
    # Cavity Liouvillian: H_cav commutator + kappa loss
    kappa = loss_params.get('kappa', 0)
    
    # Build cavity Liouvillian
    # Hamiltonian part: -i[H, rho] = -i(H*rho - rho*H)
    I_cav = identity(nmax)
    L_cav_H = -1j * (spre(H_cav) - spost(H_cav))
    
    # Dissipator: kappa * (a rho a^dag - 0.5 * {a^dag a, rho})
    if kappa > 0:
        L_cav_D = kappa * (spre(a) * spost(a.dag()) 
                          - 0.5 * spre(a.dag() * a) 
                          - 0.5 * spost(a.dag() * a))
    else:
        L_cav_D = 0 * spre(I_cav)
    
    L_cav = L_cav_H + L_cav_D
    
    # --- Combine using super_tensor ---
    # Cavity is subsystem 0, spin is subsystem 1
    I_spin = identity(nds)
    
    # Promote to full space
    L_total = qutip.super_tensor(L_cav, L_spin)  # Note: this does L_cav x I_spin + I_cav x L_spin
    
    # Wait - super_tensor doesn't add, it tensors. We need to be more careful.
    # Actually in QuTiP, super_tensor(A, B) creates the tensor product of two superoperators.
    # We need: L_cav ⊗ I_spin + I_cav ⊗ L_spin + L_int
    
    # Let me use the correct approach:
    # Create identity superoperators
    I_cav_super = qutip.to_super(I_cav)
    I_spin_super = qutip.to_super(I_spin)
    
    L_total = (qutip.super_tensor(L_cav, I_spin_super) + 
               qutip.super_tensor(I_cav_super, L_spin))
    
    # --- Interaction term ---
    # H_int = g * (a + a^dag) ⊗ Jx  (using Jx convention from doc)
    # The commutator: -i[H_int, rho] = -i(H_int * rho - rho * H_int)
    # = -i * g * ((a+a^dag)⊗Jx * rho - rho * (a+a^dag)⊗Jx)
    
    a_plus_adag = a + a.dag()
    H_int = g * tensor(a_plus_adag, jx_spin)
    
    L_int = -1j * (spre(H_int) - spost(H_int))
    L_total = L_total + L_int
    
    return L_total


def solve_steady_state(L_total):
    """
    Find the steady state density matrix of the Liouvillian.
    
    Parameters:
    -----------
    L_total : Qobj - total Liouvillian superoperator
    
    Returns:
    --------
    rho_ss : Qobj - steady state density matrix
    """
    rho_ss = steadystate(L_total)
    return rho_ss


def get_cavity_state(rho_ss, nmax, nds):
    """
    Trace out spin degrees of freedom to get the cavity reduced density matrix.
    
    Parameters:
    -----------
    rho_ss : Qobj - full steady state density matrix
    nmax : int - cavity dimension
    nds : int - number of Dicke states
    
    Returns:
    --------
    rho_cav : Qobj - reduced cavity density matrix
    """
    # Cavity is subsystem 0, spin is subsystem 1
    # ptrace(0) keeps subsystem 0 (cavity)
    rho_cav = rho_ss.ptrace(0)
    return rho_cav


def compute_wigner(rho_cav, xvec, pvec):
    """
    Compute the Wigner function of the cavity state.
    
    Parameters:
    -----------
    rho_cav : Qobj - cavity density matrix
    xvec : array - x coordinates
    pvec : array - p coordinates (not used directly by qutip.wigner, 
           but we verify they match xvec)
    
    Returns:
    --------
    W : 2D array - Wigner function values, shape (len(xvec), len(pvec))
    """
    # QuTiP's wigner function takes a state and x coordinates
    # It returns W(x, p) where both x and p use the same xvec
    # Since our grid is symmetric (same range for x and p), this works
    W = wigner(rho_cav, xvec, pvec)
    return W


def run_case(case_num, N, omega0, omegac, g, nmax, loss_params, xvec, pvec, output_dir):
    """
    Run a single case: build system, solve, compute Wigner, save.
    
    Parameters:
    -----------
    case_num : int - case number (1-4)
    N, omega0, omegac, g, nmax : model parameters
    loss_params : dict - loss channel rates
    xvec, pvec : arrays - grid coordinates
    output_dir : str - directory to save CSV
    
    Returns:
    --------
    W : 2D array - Wigner function
    """
    import os
    
    print(f"Case {case_num}: Building Liouvillian...")
    L = build_dicke_system(N, omega0, omegac, g, nmax, loss_params)
    
    print(f"Case {case_num}: Solving steady state...")
    rho_ss = solve_steady_state(L)
    
    # Validate
    nds = qutip.piqs.num_dicke_states(N)
    print(f"  rho_ss dims: {rho_ss.dims}, shape: {rho_ss.shape}")
    print(f"  Trace: {rho_ss.tr():.6f}")
    
    print(f"Case {case_num}: Tracing out spins...")
    rho_cav = get_cavity_state(rho_ss, nmax, nds)
    print(f"  rho_cav dims: {rho_cav.dims}, shape: {rho_cav.shape}")
    print(f"  Cavity trace: {rho_cav.tr():.6f}")
    
    print(f"Case {case_num}: Computing Wigner function...")
    W = compute_wigner(rho_cav, xvec, pvec)
    print(f"  Wigner shape: {W.shape}")
    print(f"  Wigner min: {np.min(W):.6f}, max: {np.max(W):.6f}")
    
    # Save
    filepath = os.path.join(output_dir, f"{case_num}.csv")
    np.savetxt(filepath, W, delimiter=',')
    print(f"Case {case_num}: Saved to {filepath}")
    
    return W


def run_all_cases(output_dir="/root"):
    """
    End-to-end entry point: run all 4 cases and save CSVs.
    
    Parameters:
    -----------
    output_dir : str - directory to save output CSV files
    """
    import os
    
    # Model parameters
    N = 4
    omega0 = 1.0
    omegac = 1.0
    g = 2.0 / np.sqrt(N)
    kappa = 1.0
    nmax = 16
    
    # Grid
    xvec = np.linspace(-6, 6, 1000)
    pvec = np.linspace(-6, 6, 1000)
    
    # Define 4 cases
    cases = [
        # Case 1: Local dephasing & local pumping
        {
            'kappa': kappa,
            'gamma_phi': 0.01,
            'gamma_up': 0.1,
        },
        # Case 2: Local dephasing & local emission
        {
            'kappa': kappa,
            'gamma_phi': 0.01,
            'gamma_down': 0.1,
        },
        # Case 3: Local dephasing & local emission & collective pumping
        {
            'kappa': kappa,
            'gamma_phi': 0.01,
            'gamma_down': 0.1,
            'gamma_UP': 0.1,
        },
        # Case 4: Local dephasing & local emission & collective emission
        {
            'kappa': kappa,
            'gamma_phi': 0.01,
            'gamma_down': 0.1,
            'gamma_DOWN': 0.1,
        },
    ]
    
    results = []
    for i, loss_params in enumerate(cases, 1):
        W = run_case(i, N, omega0, omegac, g, nmax, loss_params, xvec, pvec, output_dir)
        results.append(W)
    
    return results


def validate_outputs(output_dir="/root"):
    """
    Validate the output CSV files.
    """
    import os
    
    all_ok = True
    wigner_data = []
    
    for i in range(1, 5):
        filepath = os.path.join(output_dir, f"{i}.csv")
        if not os.path.exists(filepath):
            print(f"FAIL: {filepath} does not exist")
            all_ok = False
            continue
        
        W = np.loadtxt(filepath, delimiter=',')
        wigner_data.append(W)
        
        # Check shape
        if W.shape != (1000, 1000):
            print(f"FAIL: {filepath} shape is {W.shape}, expected (1000, 1000)")
            all_ok = False
        else:
            print(f"OK: {filepath} shape {W.shape}")
        
        # Check finiteness
        if not np.all(np.isfinite(W)):
            print(f"FAIL: {filepath} contains non-finite values")
            all_ok = False
        else:
            print(f"OK: {filepath} all values finite")
        
        # Check normalization (integral should be ~1 for proper Wigner function)
        dx = 12.0 / 999
        dp = 12.0 / 999
        integral = np.sum(W) * dx * dp
        print(f"  {filepath}: integral = {integral:.6f} (should be ~1/pi ≈ {1/np.pi:.6f})")
        # QuTiP wigner is normalized so integral over x,p = 1
        # Actually QuTiP normalizes so that integral W dx dp = 1
        print(f"  min={np.min(W):.6f}, max={np.max(W):.6f}")
    
    # Check distinctness
    if len(wigner_data) == 4:
        for i in range(4):
            for j in range(i+1, 4):
                diff = np.max(np.abs(wigner_data[i] - wigner_data[j]))
                if diff < 1e-10:
                    print(f"FAIL: Cases {i+1} and {j+1} are identical (max diff = {diff})")
                    all_ok = False
                else:
                    print(f"OK: Cases {i+1} and {j+1} differ (max diff = {diff:.6f})")
    
    if all_ok:
        print("\nAll validations passed!")
    else:
        print("\nSome validations FAILED!")
    
    return all_ok
