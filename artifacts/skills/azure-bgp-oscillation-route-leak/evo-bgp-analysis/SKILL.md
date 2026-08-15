---
name: evo-bgp-analysis
description: "Detect BGP route oscillation and route leaks in Azure Virtual WAN topologies, evaluate candidate solutions. Use when analyzing BGP preference cycles and valley-free routing violations."
---

# BGP Route Oscillation and Leak Analysis

This skill detects BGP route oscillation (preference dependency cycles) and route leaks
(valley-free routing violations) in network topologies, then evaluates candidate solutions.

## Key Concepts

### Oscillation Detection
A preference dependency cycle exists when AS A prefers routes via AS B, and AS B prefers
routes via AS A. This creates persistent route oscillation.

### Route Leak Detection (Valley-Free)
Under the valley-free model:
- Customer-learned routes may be exported to any neighbor
- Peer-learned routes should only be exported to customers
- Provider-learned routes should only be exported to customers

A violation (leak) occurs when provider/peer-learned routes are exported to a provider or peer.

### Solution Evaluation
- **Oscillation fix**: Must break the routing preference cycle in the topology
- **Route leak fix**: Must stop the leaking AS from advertising provider/peer routes to non-customer neighbors

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-bgp-analysis/scripts')
from utils import run_analysis, validate_report

# Run end-to-end analysis
report = run_analysis('/app/data', '/app/output/oscillation_report.json')

# Validate the output
validate_report('/app/output/oscillation_report.json')
```

## Scripts

### scripts/utils.py

Core functions:

- `load_json(path)` - Load JSON file
- `detect_oscillation(preferences)` - Find preference dependency cycles
- `detect_route_leaks(route_events, relationships)` - Find valley-free violations
- `evaluate_solution_oscillation(solution_text, preferences, topology)` - Check if solution breaks cycle
- `evaluate_solution_route_leak(solution_text, route_events, relationships)` - Check if solution stops leak
- `evaluate_all_solutions(solutions, preferences, topology, route_events, relationships)` - Evaluate all solutions
- `run_analysis(data_dir, output_path)` - End-to-end entry point
- `validate_report(output_path)` - Validate output report structure and content
