import json
import os
import numpy as np
import jax
import jax.numpy as jnp
from jax import grad, vmap, jit
from jax import lax


def task_basic_reduce(input_path, output_path):
    """Compute mean of each row of array x."""
    x = jnp.array(np.load(input_path))
    result = jnp.mean(x, axis=1)
    np.save(output_path, np.array(result))
    print(f"basic_reduce: input shape {x.shape} -> output shape {result.shape}")
    return result


def task_map_square(input_path, output_path):
    """Apply square function to each element using vectorization (vmap)."""
    x = jnp.array(np.load(input_path))
    # vmap the square function over rows, then it applies elementwise
    # More idiomatically: vmap a row-level square over the batch dimension
    square_fn = lambda row: row ** 2
    result = vmap(square_fn)(x)
    np.save(output_path, np.array(result))
    print(f"map_square: input shape {x.shape} -> output shape {result.shape}")
    return result


def task_grad_logistic(input_path, output_path):
    """Compute gradient of logistic loss w.r.t. weights w.
    
    Logistic loss: L(w) = (1/N) * sum(log(1 + exp(-y_i * (x_i . w))))
    """
    data = np.load(input_path)
    x = jnp.array(data['x'])  # (20, 4)
    y = jnp.array(data['y'])  # (20,)
    w = jnp.array(data['w'])  # (4,)
    
    def logistic_loss(w):
        logits = x @ w  # (20,)
        return jnp.mean(jnp.log(1.0 + jnp.exp(-y * logits)))
    
    grad_fn = grad(logistic_loss)
    result = grad_fn(w)
    np.save(output_path, np.array(result))
    print(f"grad_logistic: w shape {w.shape} -> grad shape {result.shape}")
    return result


def task_scan_rnn(input_path, output_path):
    """Implement RNN forward pass using jax.lax.scan.
    
    h_t = tanh(Wx @ x_t + Wh @ h_{t-1} + b)
    """
    data = np.load(input_path)
    seq = jnp.array(data['seq'])    # (15, 3)
    init = jnp.array(data['init'])  # (3,)
    Wx = jnp.array(data['Wx'])      # (3, 3)
    Wh = jnp.array(data['Wh'])      # (3, 3)
    b = jnp.array(data['b'])        # (3,)
    
    def rnn_step(h, x_t):
        h_new = jnp.tanh(Wx @ x_t + Wh @ h + b)
        return h_new, h_new
    
    final_h, all_h = lax.scan(rnn_step, init, seq)
    # all_h shape: (15, 3) - sequence of hidden states
    np.save(output_path, np.array(all_h))
    print(f"scan_rnn: seq shape {seq.shape} -> output shape {all_h.shape}")
    return all_h


def task_jit_mlp(input_path, output_path):
    """Implement and JIT compile a 2-layer MLP.
    
    Layer 1: relu(X @ W1 + b1)
    Layer 2: hidden @ W2 + b2
    """
    data = np.load(input_path)
    X = jnp.array(data['X'])    # (8, 6)
    W1 = jnp.array(data['W1'])  # (6, 10)
    b1 = jnp.array(data['b1'])  # (10,)
    W2 = jnp.array(data['W2'])  # (10, 2)
    b2 = jnp.array(data['b2'])  # (2,)
    
    @jit
    def mlp_forward(X, W1, b1, W2, b2):
        hidden = jax.nn.relu(X @ W1 + b1)  # (8, 10)
        output = hidden @ W2 + b2           # (8, 2)
        return output
    
    result = mlp_forward(X, W1, b1, W2, b2)
    # Force materialization
    result = jax.block_until_ready(result)
    np.save(output_path, np.array(result))
    print(f"jit_mlp: X shape {X.shape} -> output shape {result.shape}")
    return result


def run_all_tasks(problem_json_path, base_dir):
    """Run all tasks from problem.json."""
    with open(problem_json_path, 'r') as f:
        tasks = json.load(f)
    
    task_dispatch = {
        'basic_reduce': task_basic_reduce,
        'map_square': task_map_square,
        'grad_logistic': task_grad_logistic,
        'scan_rnn': task_scan_rnn,
        'jit_mlp': task_jit_mlp,
    }
    
    for task in tasks:
        tid = task['id']
        input_path = os.path.join(base_dir, task['input'])
        output_path = os.path.join(base_dir, task['output'])
        print(f"\n--- Running task: {tid} ---")
        print(f"  Input: {input_path}")
        print(f"  Output: {output_path}")
        
        if tid in task_dispatch:
            task_dispatch[tid](input_path, output_path)
            print(f"  DONE: {tid}")
        else:
            print(f"  WARNING: Unknown task id '{tid}'")
    
    print("\n=== All tasks complete ===")


def validate_outputs(problem_json_path, base_dir):
    """Validate that all output files exist and have expected properties."""
    with open(problem_json_path, 'r') as f:
        tasks = json.load(f)
    
    all_ok = True
    for task in tasks:
        tid = task['id']
        output_path = os.path.join(base_dir, task['output'])
        if not os.path.exists(output_path):
            print(f"FAIL: {tid} - output file missing: {output_path}")
            all_ok = False
            continue
        arr = np.load(output_path)
        print(f"OK: {tid} - shape={arr.shape}, dtype={arr.dtype}, "
              f"min={arr.min():.6f}, max={arr.max():.6f}")
        if np.any(np.isnan(arr)):
            print(f"  WARNING: {tid} contains NaN values")
            all_ok = False
        if np.any(np.isinf(arr)):
            print(f"  WARNING: {tid} contains Inf values")
            all_ok = False
    
    return all_ok
