---
name: evo-fjsp-repair
description: "Repair FJSP baseline schedules to eliminate downtime violations while respecting freeze, right-shift, and policy budget constraints. Use when given manufacturing scheduling tasks with instance.txt, downtime.csv, policy.json, and baseline_solution.json."
---

# FJSP Baseline Repair Skill

## Overview
Repairs Flexible Job-Shop Scheduling baseline schedules that have downtime violations.
Produces a feasible schedule with minimized makespan while respecting:
- Machine eligibility and correct durations
- Intra-job precedence ordering
- No machine overlap (half-open intervals)
- Zero downtime violations
- Right-shift-only constraint
- Freeze policy for early operations
- Machine change and L1 shift budgets
- Makespan ratio guard

## Scripts
- `scripts/parser.py` - Parse instance, downtime, policy, baseline files
- `scripts/constraints.py` - Validation functions for all constraint types
- `scripts/solver.py` - Greedy repair algorithms with multiple strategies
- `scripts/writer.py` - Write solution.json and schedule.csv outputs
- `scripts/entrypoint.py` - End-to-end pipeline: parse, repair, validate, write

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-fjsp-repair/scripts')
from entrypoint import run, validate

# Run full pipeline
result = run('/app/data', '/app/output')

# Validate outputs
valid = validate('/app/output', '/app/data')
if not valid:
    print("Schedule has issues - check output")
```

## Algorithm
1. Parse all input files
2. Identify frozen operations (baseline start < freeze_until)
3. Identify frozen ops with downtime violations (must be reassigned)
4. Process operations in precedence-aware order (op index asc, baseline start asc)
5. For each operation, find earliest feasible start on each eligible machine
6. Select assignment minimizing end time while staying within policy budgets
7. Try multiple strategies (minimize end time vs minimize duration) and pick best
8. Write outputs and validate
