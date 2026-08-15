---
name: evo-acopf
description: "Solve AC Optimal Power Flow for MATPOWER-format networks using CasADi+IPOPT. Use when tasked with finding least-cost AC-feasible operating points and producing OPF reports."
---

# AC Optimal Power Flow Skill

Solves ACOPF for MATPOWER-format JSON networks using CasADi + IPOPT.

## Scripts

- `scripts/data_loader.py` - Load and parse MATPOWER JSON network data
- `scripts/acopf_solver.py` - Formulate and solve ACOPF NLP with CasADi
- `scripts/report_generator.py` - Compute branch flows, loading, feasibility, generate report.json
- `scripts/run_acopf.py` - End-to-end entry point and validator

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-acopf/scripts')
from run_acopf import run_acopf_pipeline, validate_report

report = run_acopf_pipeline('/root/network.json', '/root/report.json')
errors = validate_report('/root/report.json', '/root/network.json')
```

## Key Implementation Details

- Tap ratio of 0.0 treated as 1.0
- Cost function uses Pg in MW (physical units)
- Branch flows use pi-model with proper transformer asymmetry
- Shunt: positive Bs is capacitive (injects Q), positive Gs consumes P
- Angle limits and phase shifts converted from degrees to radians
- Branch loading = max(Sf, St) / rateA * 100, only for rateA > 0
- Reference bus angle fixed to 0
- Uses data-based warm start clipped to bounds
