---
name: evo-dc-dispatch
description: "Solve DC Optimal Power Flow with spinning reserves from MATPOWER-format network JSON. Produces economic dispatch report with generator outputs, reserves, line loadings, and operating margin."
---

# DC-OPF with Reserves Skill

Solves economic dispatch on a power network with:
- DC power flow (lossless, angle-based)
- Generator limits and polynomial cost minimization
- Transmission line flow limits (rateA)
- Spinning reserve requirements with capacity coupling (Pg + Rg <= Pmax)

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-dc-dispatch/scripts')
from utils import run_dcopf

# End-to-end: load network, solve, validate, write report
report = run_dcopf('/root/network.json', '/root/report.json')
```

## Key Functions

- `load_network(filepath)` - Load MATPOWER JSON
- `parse_network(data)` - Parse into structured format with bus/gen/branch/cost data
- `build_Bbus_and_Bf(net)` - Build DC power flow matrices (Bf for branch flows, Bbus for bus balance)
- `solve_dcopf_with_reserves(net)` - Formulate and solve LP with scipy.optimize.linprog (HiGHS)
- `compute_line_loading(net, solution)` - Calculate line loading percentages
- `build_report(net, solution)` - Construct output report dictionary
- `validate_report(net, solution, report)` - Verify all constraints satisfied
- `run_dcopf(input_path, output_path)` - End-to-end entry point

## Problem Formulation

Variables: Pg (generation), Rg (reserve), theta (bus angles) - all in per-unit

Objective: minimize sum(c1_i * Pg_i) for linear cost generators

Constraints:
1. Bus power balance: Cg @ Pg - Bbus @ theta = Pd + Pshift_bus
2. Line flow limits: |Bf @ theta + Pshift| <= rateA
3. Generator bounds: Pmin <= Pg <= Pmax
4. Capacity coupling: Pg + Rg <= Pmax
5. Reserve bounds: 0 <= Rg <= reserve_capacity
6. System reserve: sum(Rg) >= reserve_requirement
7. Reference bus angle = 0

## Output Format

report.json with generator_dispatch, totals, most_loaded_lines, operating_margin_MW
