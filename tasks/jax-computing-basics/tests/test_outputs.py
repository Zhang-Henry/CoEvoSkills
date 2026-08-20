"""
Use this file to define pytest tests that verify the outputs of the task.

This file will be copied to /tests/test_outputs.py and run by the /tests/test.sh file
from the working directory.
"""

import json
from pathlib import Path

import jax
import jax.numpy as jnp
import numpy as np
import pytest

# The verifier receives /tests only after the agent has finished.  Never use
# the agent-writable copies under /app to derive expected values: those files
# are task inputs for the agent, not verifier evidence.
VERIFIER_PROBLEM_FILE = Path("/tests/problem.json")
VERIFIER_DATA_DIR = Path("/tests/data")
CANDIDATE_OUTPUT_DIR = Path("/app")

# Keep the scoring contract independent of a mutable manifest.  The canonical
# manifest below is still checked so accidental task-packaging drift is caught,
# but neither task IDs nor output paths are accepted from agent-controlled data.
EXPECTED_TASKS = (
    ("basic_reduce", "data/x.npy", "basic_reduce.npy"),
    ("map_square", "data/x.npy", "map_square.npy"),
    ("grad_logistic", "data/logistic.npz", "grad_logistic.npy"),
    ("scan_rnn", "data/seq.npz", "scan_rnn.npy"),
    ("jit_mlp", "data/mlp.npz", "jit_mlp.npy"),
)


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------


def load_problem():
    with VERIFIER_PROBLEM_FILE.open(encoding="utf-8") as f:
        manifest = json.load(f)

    packaged_contract = tuple((task["id"], task["input"], task["output"]) for task in manifest)
    assert packaged_contract == EXPECTED_TASKS, "Verifier-owned JAX manifest does not match the fixed scoring contract"
    return EXPECTED_TASKS


def output_path(name):
    return CANDIDATE_OUTPUT_DIR / name


def compute_expected(task):
    """Compute an oracle output inside the verifier, after agent execution."""
    task_id, input_name, _ = task
    input_path = VERIFIER_DATA_DIR / Path(input_name).name

    if task_id == "basic_reduce":
        x = np.load(input_path)
        return np.asarray(jnp.mean(x, axis=1))

    if task_id == "map_square":
        x = np.load(input_path)
        return np.asarray(jnp.square(x))

    if task_id == "grad_logistic":
        with np.load(input_path) as data:
            x, y, w = data["x"], data["y"], data["w"]

        def loss(weights):
            logits = jnp.dot(x, weights)
            return jnp.mean(jnp.logaddexp(0, -y * logits))

        return np.asarray(jax.grad(loss)(w))

    if task_id == "scan_rnn":
        with np.load(input_path) as data:
            seq = data["seq"]
            init = data["init"]
            wx, wh, bias = data["Wx"], data["Wh"], data["b"]

        def step(hidden, item):
            updated = jnp.tanh(wx @ item + wh @ hidden + bias)
            return updated, updated

        _, states = jax.lax.scan(step, init, seq)
        return np.asarray(states)

    if task_id == "jit_mlp":
        with np.load(input_path) as data:
            x = data["X"]
            w1, b1 = data["W1"], data["b1"]
            w2, b2 = data["W2"], data["b2"]

        def mlp(values):
            hidden = jax.nn.relu(jnp.dot(values, w1) + b1)
            return jnp.dot(hidden, w2) + b2

        return np.asarray(jax.jit(mlp)(x))

    raise AssertionError(f"Unknown task id: {task_id}")


@pytest.fixture(scope="session")
def expected_outputs():
    return {task[2]: compute_expected(task) for task in load_problem()}


# ---------------------------------------------------------
# 1. File existence & basic validity
# ---------------------------------------------------------


class TestOutputFilesExist:
    """Check all required output files exist."""

    def test_all_output_files_exist(self):
        tasks = load_problem()
        for t in tasks:
            out = output_path(t[2])
            assert out.is_file(), f"Missing output file: {out}"

    def test_all_expected_outputs_computed(self, expected_outputs):
        tasks = load_problem()
        assert set(expected_outputs) == {task[2] for task in tasks}

# ---------------------------------------------------------
# 2. Shape consistency
# ---------------------------------------------------------


class TestOutputShapes:
    """Check output array shapes match ground truth."""

    def test_shapes_match(self, expected_outputs):
        tasks = load_problem()
        for t in tasks:
            task_id, _, output_name = t
            out = np.load(output_path(output_name))
            ans = expected_outputs[output_name]
            assert out.shape == ans.shape, f"Shape mismatch for {task_id}: output {out.shape}, answer {ans.shape}"


# ---------------------------------------------------------
# 3. Numerical correctness
# ---------------------------------------------------------


class TestNumericalCorrectness:
    """Check numerical equality (within tolerance)."""

    @pytest.mark.parametrize("rtol, atol", [(1e-5, 1e-6)])
    def test_allclose(self, expected_outputs, rtol, atol):
        tasks = load_problem()
        for t in tasks:
            task_id, _, output_name = t
            out = np.load(output_path(output_name))
            ans = expected_outputs[output_name]
            assert np.allclose(out, ans, rtol=rtol, atol=atol), f"Numerical mismatch in task {task_id}"


# ---------------------------------------------------------
# 4. Sanity: no duplicate task IDs
# ---------------------------------------------------------


class TestTaskIDs:
    def test_no_duplicate_ids(self):
        tasks = load_problem()
        ids = [t[0] for t in tasks]
        assert len(ids) == len(set(ids)), "Duplicate task IDs in problem.json"
