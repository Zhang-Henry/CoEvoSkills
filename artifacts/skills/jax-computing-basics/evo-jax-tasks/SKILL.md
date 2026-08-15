---
name: evo-jax-tasks
description: "I/O utilities for JAX task solving: load data, run manifests, validate outputs. Caller supplies the solver function."
---

# JAX Task I/O Utilities

```python
import sys, os
sys.path.insert(0, '/app/environment/skills/evo-jax-tasks/scripts')
from io_utils import load_input, run_manifest, validate_manifest
import jax.numpy as jnp
from jax import vmap
import numpy as np

# Define solver based on your task descriptions
def solver(desc, data):
    # Parse description and compute result using JAX
    # This is task-specific logic supplied by the caller
    pass

# Run
manifest = os.path.join(os.getcwd(), 'problem.json')
if os.path.exists(manifest):
    run_manifest(manifest, solver)
    assert validate_manifest(manifest, solver)
```

## API

- `load_input(path)` — Load .npy/.npz to dict
- `load_manifest(path)` — Load JSON manifest
- `save_result(result, path)` — Save array to .npy
- `run_manifest(path, solver_fn)` — Iterate manifest, call solver, save
- `validate_manifest(path, solver_fn)` — Re-execute, compare
