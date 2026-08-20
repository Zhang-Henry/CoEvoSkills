---
name: evo-dicke-wigner
description: "Simulate open Dicke model steady state and compute cavity Wigner function using QuTiP PIQS. Use for tasks involving Dicke model, collective spin-cavity systems, Wigner function calculation, and open quantum systems with various loss channels."
---

# Open Dicke Model Wigner Function Skill

This skill computes the steady-state Wigner function of the cavity field in an open Dicke model
using QuTiP's PIQS module for collective spin operators.

## Key Conventions

- Uses PIQS `Jx` operator (not `J+ + J-`) with coupling `g * (a + a†) ⊗ Jx`
- Builds spin Liouvillian with PIQS `Dicke` class including spin Hamiltonian
- Combines cavity and spin Liouvillians with `super_tensor`
- Adds interaction via `spre`/`spost` commutator
- Cavity is subsystem 0 for partial trace

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-dicke-wigner/scripts')
from utils import run_all_cases, validate_outputs

# Run all 4 cases and save CSVs
run_all_cases(output_dir='/root')

# Validate outputs
validate_outputs(output_dir='/root')
```

## Functions

- `build_spin_hamiltonian(N, omega0)` - Build ω₀Jz in Dicke basis
- `build_spin_liouvillian(N, omega0, ...)` - Build spin Liouvillian with PIQS Dicke
- `build_cavity_liouvillian(omega_c, n_max, kappa)` - Build cavity Liouvillian with loss
- `build_interaction_superop(N, n_max, g)` - Build interaction superoperator
- `build_full_liouvillian(...)` - Combine all parts into full Liouvillian
- `find_steady_state(L)` - Find steady state density matrix
- `get_cavity_state(rho_ss, n_max, nds)` - Trace out spins
- `compute_wigner(rho_cav, xvec, yvec)` - Compute Wigner function
- `save_wigner_csv(W, filepath)` - Save as CSV
- `run_case(...)` - Run single case end-to-end
- `run_all_cases(output_dir)` - Run all 4 cases
- `validate_outputs(output_dir)` - Validate all outputs
