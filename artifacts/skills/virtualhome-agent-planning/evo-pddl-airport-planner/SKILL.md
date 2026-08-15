---
name: evo-pddl-airport-planner
description: "Solve PDDL airport ground-traffic planning tasks from IPC problem suites. Use when given PDDL domain and problem files for airport domains with aircraft taxiing, parking, pushback, and takeoff. Reads problem.json, solves each task with pyperplan, and writes plans in standard PDDL format."
---

# PDDL Airport Planner

Solves PDDL planning tasks for airport ground-traffic control domains from IPC competitions.

## Overview

- Reads `problem.json` listing tasks with domain/problem PDDL file paths and output paths
- Uses `pyperplan` directly for parsing, grounding, and search (hFF + A*, fallback to BFS)
- Outputs plans in standard PDDL parenthesized format: `(action_name arg1 arg2 ...)`
- One action per line, lowercase (PDDL is case-insensitive)

## Dependencies

- `pyperplan` (2.1+)
- Python 3.10+

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-pddl-airport-planner/scripts')
from solve import solve_all_tasks, validate_plans

# Solve all tasks from problem.json
results = solve_all_tasks('/app/problem.json', base_dir='/app')

# Validate outputs
valid = validate_plans('/app/problem.json', base_dir='/app')
assert valid, "Some plans failed validation"
print("All tasks solved successfully!")
```

## Utility Functions (scripts/utils.py)

### `load_tasks(problem_json_path)`
Load task definitions from problem.json. Returns list of task dicts.

### `solve_pddl_task(domain_path, problem_path)`
Solve a single PDDL task using pyperplan BFS. Returns list of action strings
in standard PDDL format `(action_name arg1 ...)` or None.

### `solve_pddl_task_with_heuristic(domain_path, problem_path)`
Solve using hFF heuristic with A* search, falling back to BFS.
Returns list of action strings or None.

### `write_plan(actions, output_path)`
Write action list to a plan file, one action per line.

### `solve_and_write(domain_path, problem_path, output_path)`
Solve and write in one call. Returns True on success.

## Entry Points (scripts/solve.py)

### `solve_all_tasks(problem_json_path, base_dir=None)`
End-to-end: reads problem.json, solves all tasks, writes all plan files.
Returns dict of task_id -> success boolean.

### `validate_plans(problem_json_path, base_dir=None)`
Checks all output files exist, are non-empty, and have valid PDDL action syntax.

## Key Design Decisions

1. **Direct pyperplan**: Uses pyperplan directly instead of through unified_planning
   to get native PDDL plan format without case conversion issues.

2. **Standard PDDL format**: Plans use `(action_name arg1 arg2)` parenthesized
   format with space-separated arguments, which is the standard IPC plan format.

3. **Heuristic search with fallback**: Tries hFF + A* first for efficiency on
   larger instances, falls back to BFS if heuristic search fails.
