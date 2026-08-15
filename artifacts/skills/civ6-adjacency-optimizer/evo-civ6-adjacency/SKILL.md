---
name: evo-civ6-adjacency
description: "Optimize Civ6 district placement for maximum adjacency bonuses. Use when given a .Civ6Map file and scenario parameters (num_cities, population, civilization). Reads map as SQLite, computes hex grid neighbors, validates placement rules, calculates adjacency bonuses per district type, and uses greedy optimization to find best layout."
---

# Civ6 District Adjacency Bonus Optimizer

## Overview
Solves Civilization 6 district placement optimization problems. Given a map file
and scenario parameters, finds optimal city center and district placements to
maximize total adjacency bonuses.

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-civ6-adjacency/scripts')
from main import solve_scenario, validate_output

# Caller must supply runtime paths from the task instruction
scenario_path = '/data/scenario_3/scenario.json'  # adapt per task
output_path = '/output/scenario_3.json'            # adapt per task

solve_scenario(scenario_path, output_path)
validate_output(output_path, scenario_path)
```

## Architecture

### Scripts

- **hex_utils.py**: Hex grid math (odd-r offset neighbors, cube distance)
- **map_reader.py**: SQLite reader for .Civ6Map files, terrain/feature/river helpers,
  runtime resource classification (strategic/luxury/bonus derived from name patterns)
- **placement.py**: District placement validation; `build_district_categories()` derives
  specialty/non-specialty/no-bonus sets from the public Gathering Storm ruleset
- **adjacency.py**: Per-district adjacency bonus calculation with flooring rules
- **optimizer.py**: Greedy optimizer that scores candidate placements; derives district
  priorities and search breadth from categories and map size at runtime
- **main.py**: End-to-end entry point (requires scenario_path and output_path arguments)
- **validator.py**: Solution validation

### Key Design Decisions

1. **Odd-r offset coordinates**: Even rows use different neighbor offsets than odd rows
2. **River detection**: Must check both own flags AND complementary neighbor flags
3. **Feature destruction**: Placing districts (except CC) destroys forests/jungles/marshes
4. **Minor bonus flooring**: Each source type floored independently
5. **Non-specialty districts are powerful**: Aqueduct/Dam/Neighborhood boost neighbors for free
6. **Runtime resource classification**: Resources classified as strategic/luxury/bonus from
   name patterns at runtime rather than hardcoded lists
7. **Runtime-derived priorities**: District search priorities derived from categories;
   search breadth scales with map size
8. **Greedy search**: Iteratively adds best (district, position) pair; supports multiple
   neighborhoods via indexed keys

### Adjacency Rules Summary

| District | Major Bonuses | Minor Bonuses |
|----------|--------------|---------------|
| Campus | +2 geothermal/reef, +1 mountain | +1 per 2 jungles, +1 per 2 districts |
| Holy Site | +1 mountain | +1 per 2 forests, +1 per 2 districts |
| Commercial Hub | +2 river (self-tile), +2 harbor | +1 per 2 districts |
| Industrial Zone | +2 aqueduct/dam/canal | +1 per 2 districts |
| Harbor | +2 city center | +1 per 2 districts |
| Theater Square | +2 entertainment complex | +1 per 2 districts |

### Optimization Notes

The greedy optimizer may miss globally optimal solutions when early placements
prevent better late placements. For best results, the caller should also try
multiple district priority orderings via the spec_priority and nonspec_priority
parameters of greedy_optimize().
