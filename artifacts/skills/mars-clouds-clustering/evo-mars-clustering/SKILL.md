---
name: evo-mars-clustering
description: "DBSCAN hyperparameter grid search for Mars cloud clustering with Pareto frontier extraction. Use when optimizing DBSCAN parameters (min_samples, epsilon, shape_weight) to cluster citizen science annotations against expert labels."
---

# Mars Cloud Clustering Optimization

This skill performs DBSCAN hyperparameter optimization for clustering citizen science
annotations of Mars clouds, finding the Pareto frontier balancing F1 score and delta.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-mars-clustering/scripts')
from utils import run_pipeline

result = run_pipeline(
    citsci_path='/root/data/citsci_train.csv',
    expert_path='/root/data/expert_train.csv',
    output_path='/root/pareto_frontier.csv',
    n_jobs=-1,
    max_evaluations=1000,
    deadline_seconds=600
)
```

## Key Functions

- `load_data(citsci_path, expert_path)` - Load and group data by file_rad
- `compute_weighted_distance_matrix(points, shape_weight)` - Custom weighted distance
- `run_dbscan_on_image(points, min_samples, epsilon, shape_weight)` - DBSCAN clustering
- `greedy_match(centroids, expert_points, max_dist=100)` - Greedy centroid matching
- `evaluate_image(citsci_pts, expert_pts, ms, eps, sw)` - Per-image evaluation
- `evaluate_hyperparams(ms, eps, sw, citsci_grouped, expert_grouped, images)` - Full eval
- `generate_param_grid()` - Generate parameter grid
- `run_grid_search(citsci_path, expert_path, n_jobs, max_evaluations, deadline_seconds)` - Parallel grid search with budget
- `compute_pareto_frontier(results_df, f1_threshold=0.5)` - Pareto extraction
- `format_and_save(pareto_df, output_path)` - Format and save CSV
- `run_pipeline(...)` - End-to-end with budget guards
