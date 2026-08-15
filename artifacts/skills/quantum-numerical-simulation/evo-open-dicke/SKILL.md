---
name: evo-open-dicke
description: "Simulate an open Dicke model using QuTiP PIQS, compute steady-state cavity Wigner functions for multiple loss cases, and save as CSV files."
---

# Open Dicke Model Wigner Function Simulation

This skill simulates an open Dicke model composed of N identical two-level systems
coupled to a cavity mode. It computes the steady-state density matrix, traces out
the spin degrees of freedom, and calculates the cavity field Wigner function.

## Key Conventions

- Uses PIQS `Dicke` class for collective spin operators in Dicke basis
- Interaction Hamiltonian uses Jx convention: `H_int = g * tensor(a + a.dag(), jx)`
- No extra factor of 2 (J+ + J- = 2*Jx is absorbed into the coupling coefficient)
- Cavity is subsystem 0, spin is subsystem 1
- Liouvillian built using `super_tensor` for cavity and spin parts, plus interaction commutator

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-open-dicke/scripts')
from utils import run_all_cases, validate_outputs

# Run all 4 cases and save CSVs
results = run_all_cases(output_dir='/root')

# Validate outputs
validate_outputs(output_dir='/root')
```

## Functions

- `build_dicke_system(N, omega0, omegac, g, nmax, loss_params)` - Build full Liouvillian
- `solve_steady_state(L_total)` - Find steady state
- `get_cavity_state(rho_ss, nmax, nds)` - Trace out spins
- `compute_wigner(rho_cav, xvec, pvec)` - Compute Wigner function
- `run_case(case_num, ...)` - Run single case end-to-end
- `run_all_cases(output_dir)` - Run all 4 cases
- `validate_outputs(output_dir)` - Validate output files
