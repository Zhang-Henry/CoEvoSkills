---
name: evo-jax-tasks
description: "Solve JAX numerical computing tasks from a problem.json manifest. Handles reductions, vmap, grad, scan, and jit tasks."
---

# JAX Task Solver Skill

This skill solves sets of JAX programming tasks specified in a problem.json manifest.

## Supported Task Types

- **basic_reduce**: Row-wise mean reduction
- **map_square**: Element-wise squaring via vmap
- **grad_logistic**: Gradient of logistic loss via jax.grad
- **scan_rnn**: RNN forward pass via jax.lax.scan
- **jit_mlp**: JIT-compiled 2-layer MLP forward pass

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-jax-tasks/scripts')
from utils import run_all_tasks, validate_outputs

# Run all tasks
run_all_tasks('/app/problem.json', '/app')

# Validate outputs
validate_outputs('/app/problem.json', '/app')
```

## Individual Task Functions

Each task function takes (input_path, output_path) and returns the JAX result:

```python
from utils import task_basic_reduce, task_map_square, task_grad_logistic, task_scan_rnn, task_jit_mlp
```
