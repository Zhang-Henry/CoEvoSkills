---
name: evo-acc-simulation
description: Reusable evolved utilities for acc simulation; use for closely related task execution and validation.
---

# Acc Simulation

This recovery manifest preserves utility scripts produced by the evolution agent when its context budget ended before documentation was written. Read the scripts before use and call their helpers instead of duplicating their logic.

## Available helpers

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-acc-simulation/scripts')
import acc_system
import pid_controller
from simulation import load_sensor_data, run_simulation, analyze
```
