"""I/O utilities for JAX task solving."""
import numpy as np
import json
import os


def load_input(path):
    """Load .npy or .npz file, returning dict of numpy arrays."""
    if path.endswith('.npz'):
        d = np.load(path)
        return {k: d[k] for k in d.files}
    return {'array': np.load(path)}


def load_manifest(path):
    """Load a JSON task manifest."""
    with open(path) as f:
        return json.load(f)


def save_result(result, path):
    """Save a JAX/numpy array to .npy file."""
    np.save(path, np.asarray(result))


def resolve_paths(task, base_dir):
    """Resolve input/output paths relative to base_dir."""
    return (
        os.path.join(base_dir, task['input']),
        os.path.join(base_dir, task['output'])
    )


def run_manifest(manifest_path, solver_fn, base_dir=None):
    """Load manifest, call solver_fn(description, data) for each task, save results."""
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(manifest_path))
    tasks = load_manifest(manifest_path)
    for t in tasks:
        inp, out = resolve_paths(t, base_dir)
        data = load_input(inp)
        result = solver_fn(t['description'], data)
        save_result(result, out)
        print(f"{t['id']}: {np.asarray(result).shape} -> {out}")


def validate_manifest(manifest_path, solver_fn, base_dir=None):
    """Re-execute and compare with saved outputs."""
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(manifest_path))
    tasks = load_manifest(manifest_path)
    ok = True
    for t in tasks:
        inp, out = resolve_paths(t, base_dir)
        if not os.path.exists(out):
            print(f"FAIL {t['id']}: missing"); ok = False; continue
        saved = np.load(out)
        data = load_input(inp)
        recomp = np.asarray(solver_fn(t['description'], data))
        if np.allclose(saved, recomp, rtol=1e-6, atol=1e-6):
            print(f"OK {t['id']}: {saved.shape}")
        else:
            print(f"FAIL {t['id']}: mismatch"); ok = False
    return ok
