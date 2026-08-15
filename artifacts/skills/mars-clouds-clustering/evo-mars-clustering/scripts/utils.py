import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from joblib import Parallel, delayed
import time
import warnings
warnings.filterwarnings('ignore')


def load_data(citsci_path, expert_path):
    """Load and preprocess citizen science and expert data."""
    citsci = pd.read_csv(citsci_path, usecols=['file_rad', 'x', 'y'])
    expert = pd.read_csv(expert_path, usecols=['file_rad', 'x', 'y'])
    
    citsci_grouped = {}
    for fr, grp in citsci.groupby('file_rad'):
        citsci_grouped[fr] = grp[['x', 'y']].values.astype(np.float64)
    
    expert_grouped = {}
    for fr, grp in expert.groupby('file_rad'):
        expert_grouped[fr] = grp[['x', 'y']].values.astype(np.float64)
    
    all_expert_images = sorted(expert['file_rad'].unique())
    
    return citsci_grouped, expert_grouped, all_expert_images


def compute_weighted_distance_matrix(points, shape_weight):
    """Compute pairwise weighted distance matrix."""
    w = shape_weight
    n = len(points)
    if n == 0:
        return np.zeros((0, 0))
    x = points[:, 0]
    y = points[:, 1]
    dx = x[:, None] - x[None, :]
    dy = y[:, None] - y[None, :]
    dist = np.sqrt((w * dx)**2 + ((2 - w) * dy)**2)
    return dist


def run_dbscan_on_image(points, min_samples, epsilon, shape_weight):
    """Run DBSCAN on points for a single image. Returns cluster centroids."""
    if len(points) == 0:
        return np.zeros((0, 2))
    dist_matrix = compute_weighted_distance_matrix(points, shape_weight)
    db = DBSCAN(eps=epsilon, min_samples=min_samples, metric='precomputed')
    labels = db.fit_predict(dist_matrix)
    unique_labels = set(labels)
    unique_labels.discard(-1)
    if not unique_labels:
        return np.zeros((0, 2))
    centroids = []
    for label in sorted(unique_labels):
        mask = labels == label
        centroid = points[mask].mean(axis=0)
        centroids.append(centroid)
    return np.array(centroids)


def greedy_match(centroids, expert_points, max_dist=100.0):
    """Greedy matching: closest pairs first, max distance threshold."""
    nc = len(centroids)
    ne = len(expert_points)
    if nc == 0 or ne == 0:
        return 0, 0.0, nc, ne
    dx = centroids[:, 0:1] - expert_points[:, 0:1].T
    dy = centroids[:, 1:2] - expert_points[:, 1:2].T
    dists = np.sqrt(dx**2 + dy**2)
    matched = 0
    total_dist = 0.0
    used_c = set()
    used_e = set()
    while True:
        mask = np.full(dists.shape, np.inf)
        for i in range(nc):
            if i in used_c:
                continue
            for j in range(ne):
                if j in used_e:
                    continue
                mask[i, j] = dists[i, j]
        min_val = mask.min()
        if min_val > max_dist or np.isinf(min_val):
            break
        idx = np.unravel_index(mask.argmin(), mask.shape)
        used_c.add(idx[0])
        used_e.add(idx[1])
        matched += 1
        total_dist += min_val
    return matched, total_dist, nc, ne


def evaluate_image(citsci_points, expert_points, min_samples, epsilon, shape_weight):
    """Evaluate one image: run DBSCAN, match, compute F1 and delta."""
    if citsci_points is None or len(citsci_points) == 0:
        return 0.0, float('nan')
    centroids = run_dbscan_on_image(citsci_points, min_samples, epsilon, shape_weight)
    if len(centroids) == 0:
        return 0.0, float('nan')
    tp, total_dist, nc, ne = greedy_match(centroids, expert_points, max_dist=100.0)
    if tp == 0:
        return 0.0, float('nan')
    fp = nc - tp
    fn = ne - tp
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    delta = total_dist / tp
    return f1, delta


def evaluate_hyperparams(min_samples, epsilon, shape_weight, citsci_grouped, expert_grouped, all_expert_images):
    """Evaluate a single hyperparameter combination across all images."""
    f1_scores = []
    deltas = []
    for img in all_expert_images:
        expert_pts = expert_grouped[img]
        citsci_pts = citsci_grouped.get(img, None)
        f1, delta = evaluate_image(citsci_pts, expert_pts, min_samples, epsilon, shape_weight)
        f1_scores.append(f1)
        if not np.isnan(delta):
            deltas.append(delta)
    avg_f1 = np.mean(f1_scores)
    avg_delta = np.mean(deltas) if deltas else float('nan')
    return avg_f1, avg_delta, min_samples, epsilon, shape_weight


def generate_param_grid():
    """Generate the parameter grid as a list of tuples."""
    params = []
    for ms in range(3, 10):
        for eps in range(4, 25, 2):
            for sw_i in range(11):
                sw = round(0.9 + sw_i * 0.1, 1)
                params.append((ms, eps, sw))
    return params


def run_grid_search(citsci_path, expert_path, n_jobs=-1, max_evaluations=1000, deadline_seconds=600):
    """Run grid search with explicit budget guards.
    
    Args:
        max_evaluations: Maximum number of hyperparameter combos to evaluate.
        deadline_seconds: Maximum wall-clock time in seconds.
    
    Raises:
        RuntimeError if budget is exhausted before completion.
    """
    start_time = time.time()
    citsci_grouped, expert_grouped, all_expert_images = load_data(citsci_path, expert_path)
    
    param_combos = generate_param_grid()
    total = len(param_combos)
    
    if total > max_evaluations:
        raise RuntimeError(f"Grid has {total} combos but max_evaluations={max_evaluations}. Increase budget or reduce grid.")
    
    print(f"Total combinations: {total} (budget: {max_evaluations})")
    print(f"Deadline: {deadline_seconds}s")
    print(f"Total expert images: {len(all_expert_images)}")
    
    results = Parallel(n_jobs=n_jobs, verbose=5)(
        delayed(evaluate_hyperparams)(ms, eps, sw, citsci_grouped, expert_grouped, all_expert_images)
        for ms, eps, sw in param_combos
    )
    
    elapsed = time.time() - start_time
    if elapsed > deadline_seconds:
        raise RuntimeError(f"Deadline exceeded: {elapsed:.1f}s > {deadline_seconds}s")
    
    print(f"Grid search completed in {elapsed:.1f}s")
    df = pd.DataFrame(results, columns=['F1', 'delta', 'min_samples', 'epsilon', 'shape_weight'])
    return df


def compute_pareto_frontier(results_df, f1_threshold=0.5):
    """Filter results and compute Pareto frontier."""
    from paretoset import paretoset
    filtered = results_df[
        (results_df['F1'] > f1_threshold) & 
        (np.isfinite(results_df['delta']))
    ].copy()
    if len(filtered) == 0:
        return pd.DataFrame(columns=['F1', 'delta', 'min_samples', 'epsilon', 'shape_weight'])
    mask = paretoset(filtered[['F1', 'delta']], sense=['max', 'min'])
    pareto = filtered[mask].copy()
    return pareto


def format_and_save(pareto_df, output_path):
    """Format and save Pareto frontier to CSV."""
    out = pareto_df.copy()
    out['F1'] = out['F1'].round(5)
    out['delta'] = out['delta'].round(5)
    out['shape_weight'] = out['shape_weight'].round(1)
    out['min_samples'] = out['min_samples'].astype(int)
    out['epsilon'] = out['epsilon'].astype(int)
    out = out[['F1', 'delta', 'min_samples', 'epsilon', 'shape_weight']]
    out.to_csv(output_path, index=False)
    print(f"Saved {len(out)} Pareto-optimal points to {output_path}")
    return out


def run_pipeline(citsci_path, expert_path, output_path, n_jobs=-1, max_evaluations=1000, deadline_seconds=600):
    """End-to-end pipeline with budget guards."""
    print("Starting grid search...")
    results = run_grid_search(citsci_path, expert_path, n_jobs=n_jobs,
                              max_evaluations=max_evaluations,
                              deadline_seconds=deadline_seconds)
    print(f"Grid search complete. {len(results)} results.")
    print(f"Results with F1 > 0.5: {(results['F1'] > 0.5).sum()}")
    pareto = compute_pareto_frontier(results)
    print(f"Pareto frontier: {len(pareto)} points")
    output = format_and_save(pareto, output_path)
    print(output)
    return output
