#!/usr/bin/env bash
set -euo pipefail

cd /app
python3 <<'PY'
import json
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np


root = Path("/app")
tasks = json.loads((root / "problem.json").read_text(encoding="utf-8"))

for task in tasks:
    task_id = task["id"]
    input_path = root / task["input"]

    if task_id == "basic_reduce":
        result = jnp.mean(np.load(input_path), axis=1)
    elif task_id == "map_square":
        result = jnp.square(np.load(input_path))
    elif task_id == "grad_logistic":
        with np.load(input_path) as data:
            x, y, weights = data["x"], data["y"], data["w"]

        def loss(candidate):
            logits = jnp.dot(x, candidate)
            return jnp.mean(jnp.logaddexp(0, -y * logits))

        result = jax.grad(loss)(weights)
    elif task_id == "scan_rnn":
        with np.load(input_path) as data:
            sequence = data["seq"]
            initial = data["init"]
            wx, wh, bias = data["Wx"], data["Wh"], data["b"]

        def step(hidden, item):
            updated = jnp.tanh(wx @ item + wh @ hidden + bias)
            return updated, updated

        _, result = jax.lax.scan(step, initial, sequence)
    elif task_id == "jit_mlp":
        with np.load(input_path) as data:
            values = data["X"]
            w1, b1 = data["W1"], data["b1"]
            w2, b2 = data["W2"], data["b2"]

        @jax.jit
        def mlp(items):
            hidden = jax.nn.relu(jnp.dot(items, w1) + b1)
            return jnp.dot(hidden, w2) + b2

        result = mlp(values)
    else:
        raise ValueError(f"unknown task id: {task_id}")

    np.save(root / task["output"], np.asarray(result))
PY
