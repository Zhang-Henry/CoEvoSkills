---
name: evo-dcopf-market
description: "DC-OPF with reserve co-optimization market clearing solver. Solves base and counterfactual scenarios for transmission constraint analysis."
---

# DC-OPF Market Clearing with Reserve Co-optimization

## Overview

This skill implements a DC Optimal Power Flow (DC-OPF) solver with spinning reserve
co-optimization for day-ahead electricity market clearing analysis.

## Key Concepts

### DC-OPF Formulation
- Variables: generator power (pg), reserve (rv), bus angles (theta)
- Objective: minimize total generation cost
- Constraints:
  1. Power balance at each bus (gen - demand = net flow)
  2. Branch flow = baseMVA * (theta_from - theta_to) / reactance
  3. Branch flow limits: -rateA <= flow <= rateA
  4. Generator limits: Pmin <= pg <= Pmax
  5. Capacity coupling: pg + rv <= Pmax
  6. Reserve limits: 0 <= rv <= reserve_capacity
  7. System reserve: sum(rv) >= reserve_requirement
  8. Reference bus angle = 0

### LMP and Reserve MCP
- LMP at each bus = dual value of power balance constraint
- Reserve MCP = dual value of system reserve requirement constraint

### Binding Lines
- Lines where |flow| / rateA >= 0.99 (99% loading)

## Scripts

- `scripts/solver.py`: Main solver with all functions

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-dcopf-market/scripts')
from solver import run_analysis, validate_report

report = run_analysis(
    network_path='/root/network.json',
    output_path='/root/report.json',
    from_bus=64,
    to_bus=1501,
    capacity_increase=0.20
)

validate_report('/root/report.json')
```

## Dependencies
- numpy
- pulp (with CBC solver)
