# DBSCAN Clustering with Custom Metrics and Pareto Optimization

This document provides background on density-based clustering, weighted distance metrics, greedy centroid matching, F1 evaluation, and multi-objective Pareto frontier extraction -- the core techniques needed to optimize citizen science annotation clustering against expert labels.

## Citizen Science Annotation Aggregation

Citizen science projects collect annotations from many non-expert volunteers. For image annotation tasks (such as marking features in planetary images), multiple volunteers mark the same image, producing a cloud of nearby but not identical points around each real feature. The goal of clustering is to aggregate these noisy individual marks into a single consensus location per feature.

The fundamental challenge is that citizen annotations exhibit two kinds of variation. **Intra-feature scatter** is the spread of marks around a genuine feature -- these marks should be grouped into one cluster. **Inter-feature separation** is the distance between distinct features -- these groups should remain separate clusters. A good clustering configuration finds the boundary between these two regimes.

The `file_rad` column in the data identifies unique base images. Multiple annotation records may exist per image (from different volunteers), and the same base image may appear with different filename suffixes in the raw data. Grouping by `file_rad` ensures that all annotations for the same physical image are clustered together, regardless of which image variant a volunteer happened to view.

## DBSCAN: Density-Based Spatial Clustering

DBSCAN (Density-Based Spatial Clustering of Applications with Noise) groups points based on local density rather than global shape assumptions. It requires two parameters:

- **epsilon** -- the maximum distance between two points for them to be considered neighbors.
- **min_samples** -- the minimum number of points within epsilon distance required to form a dense region (a core point).

A core point is any point with at least `min_samples` neighbors within its epsilon-radius neighborhood (including itself, in scikit-learn's implementation). Clusters grow by chaining: if point B is within epsilon of core point A, B joins A's cluster; if B is also a core point, its neighbors transitively join as well. Points that are within epsilon of a core point but are not themselves core points become **border points** of that cluster. Points that are not within epsilon of any core point are labeled **noise** (label -1) and do not belong to any cluster.

Key behavioral properties relevant to hyperparameter tuning:

- **Increasing epsilon** makes the neighborhood radius larger, which tends to merge nearby clusters into larger ones and reduces noise. Too large an epsilon collapses distinct features into a single cluster.
- **Increasing min_samples** raises the density threshold, requiring more annotations in a neighborhood before a core point can form. This suppresses clusters in sparsely annotated regions and increases the number of noise points.
- When the number of data points in an image is fewer than `min_samples`, DBSCAN will label every point as noise and produce zero clusters. This is correct behavior -- the algorithm should still run (not be short-circuited), because the absence of clusters is a meaningful result that feeds into downstream F1 computation.

### Cluster Centroids

After DBSCAN assigns labels, the centroid of each cluster is computed as the arithmetic mean of the (x, y) coordinates of all points assigned to that cluster (excluding noise points). These centroids represent the consensus location of each detected feature and serve as the predicted positions to compare against expert annotations.

## Custom Weighted Distance Metrics

Standard Euclidean distance treats the x-axis and y-axis equally:

The distance `d(a, b)` equals the square root of `dx` squared plus `dy` squared.

A weighted distance metric introduces a parameter `w` (shape_weight) that controls the relative importance of each axis:

The weighted distance `d(a, b)` equals the square root of (`w` times `dx`) squared plus ((`2 - w`) times `dy`) squared.

When `w = 1`, this reduces to standard Euclidean distance because both axes are scaled by 1. When `w > 1`, the x-axis is amplified while the y-axis is attenuated (since `2 - w < 1`), making the clustering more sensitive to horizontal separation. When `w < 1`, the reverse occurs.

This matters because features in many image annotation datasets are not isotropically distributed. Clouds in orbital imagery, for example, may be elongated along one axis due to atmospheric dynamics or instrument geometry. The shape weight lets DBSCAN adapt its neighborhood shape from a circle (w=1) to an ellipse aligned with the axis that exhibits more meaningful variation.

**Implementation detail**: When using DBSCAN with a custom metric, the most efficient approach is to precompute the full pairwise distance matrix using the weighted formula and pass it to the algorithm with a precomputed distance setting. The precomputed matrix is symmetric, with entry [i][j] giving the weighted distance between points i and j. This avoids repeated distance calculations during neighborhood queries.

## Greedy Centroid-to-Expert Matching

Once cluster centroids are computed, they must be matched against expert annotations to evaluate quality. The matching procedure is a greedy bipartite assignment:

1. Compute the pairwise **standard Euclidean distance** (not the custom weighted distance) between all cluster centroids and all expert points for the image.
2. Find the globally closest (centroid, expert) pair.
3. If that distance is below the maximum matching threshold, record it as a match and remove both the centroid and expert point from further consideration.
4. Repeat until no remaining pair is below the threshold.

This greedy approach does not guarantee an optimal assignment (the Hungarian algorithm would), but it is the specified method. The order in which ties are broken can affect results, so the implementation should find the single global minimum at each step.

The distances recorded from successful matches are used to compute the delta metric. It is critical that matching uses standard Euclidean distance, not the weighted distance used for clustering -- these are distinct operations with different purposes.

## F1 Score for Cluster Evaluation

The F1 score measures agreement between predicted clusters and expert annotations using precision-recall semantics adapted from information retrieval:

- **True Positive (TP)**: A cluster centroid that was successfully matched to an expert point.
- **False Positive (FP)**: A cluster centroid that could not be matched to any expert point (spurious detection).
- **False Negative (FN)**: An expert point that was not matched to any cluster centroid (missed detection).

From these counts:

Precision is computed as `TP / (TP + FP)`, Recall as `TP / (TP + FN)`, and F1 as `2 * Precision * Recall / (Precision + Recall)`.

When there are no true positives (TP = 0), F1 is 0. This occurs when DBSCAN produces no clusters, when no centroids are close enough to any expert point, or when the image has no citizen science annotations at all.

### Averaging Across Images

The evaluation iterates over all unique images present in the expert dataset -- not just images that also have citizen science annotations. This is an important distinction:

- **F1 averaging**: Every image contributes. Images with no citizen science data, no formed clusters, or no matches contribute F1 = 0. This penalizes hyperparameter settings that fail to produce clusters on many images.
- **Delta averaging**: Only images where at least one match was found contribute to the delta average. Images with no matches contribute NaN for delta, and these NaN values are excluded (not treated as zero). This prevents the delta metric from being distorted by images that have no meaningful positional error to measure.

This asymmetry is deliberate: F1 measures detection coverage (every image matters, even failures), while delta measures positional accuracy (only meaningful where detection succeeded).

## Multi-Objective Optimization and Pareto Frontiers

This task involves two competing objectives: maximize F1 (detection quality) and minimize delta (positional accuracy). No single hyperparameter setting will simultaneously achieve the best possible F1 and the best possible delta, because the objectives trade off against each other. For example, larger epsilon values may detect more features (higher recall, higher F1) but merge nearby features into less precise centroids (higher delta).

A **Pareto frontier** (also called a Pareto front or Pareto-optimal set) is the set of solutions where no other solution is strictly better on all objectives. Formally, solution A **dominates** solution B if A is at least as good as B on every objective and strictly better on at least one. A solution is **Pareto-optimal** if no other solution in the candidate set dominates it.

For two objectives (maximize F1, minimize delta):

- Solution A dominates solution B if `A.F1 >= B.F1` and `A.delta <= B.delta`, with at least one strict inequality.
- The Pareto frontier consists of all solutions that are not dominated by any other solution.

The `paretoset` library can compute this efficiently given a DataFrame of objective values and a sense specification (which objectives to maximize vs. minimize).

### Filtering Before Pareto Computation

Not all hyperparameter combinations produce useful results. A minimum F1 threshold (above 0.5) filters out configurations that fail to achieve meaningful clustering performance. Only results passing this filter are candidates for the Pareto frontier. Configurations that produce `inf` or undefined delta values (because no matches were ever found across all images) should also be excluded.

## Grid Search Strategy

The hyperparameter space is searched exhaustively over a discrete grid. With three parameters (min_samples, epsilon, shape_weight), the total number of combinations is the product of the number of values for each parameter. Each combination is evaluated independently across all images, making the search embarrassingly parallel -- the evaluation of one hyperparameter setting does not depend on any other.

Parallel execution across CPU cores is an effective way to accelerate the grid search. Each parallel worker evaluates one (min_samples, epsilon, shape_weight) tuple over the full set of images and returns the aggregated F1 and delta.

Pre-grouping the data by image before the grid search avoids repeated filtering operations inside the inner loop. Converting the grouped data to numerical arrays (rather than keeping them as higher-level data structures) further reduces overhead since the clustering and distance computations operate on numerical arrays.

## Key Distinctions in Practice

- **The weighted distance metric applies only to the clustering step.** Centroid-to-expert matching and the delta metric both use standard Euclidean distance. These are distinct operations with different purposes, and mixing them produces incorrect F1 and delta values.

- **DBSCAN should always be invoked, even when few points are available.** When an image has fewer citizen science points than min_samples, DBSCAN correctly classifies all points as noise and produces zero clusters. The algorithm's own noise-handling behavior is the authoritative result, and bypassing it with manual short-circuit logic can introduce subtle discrepancies.

- **The evaluation iterates over all images in the expert dataset, not just those with citizen science annotations.** Images where experts found features but no volunteers annotated them contribute F1 = 0 to the average. This ensures that the reported F1 reflects true detection coverage, including images that were missed entirely.

- **NaN delta values (from images with zero matches) are excluded from the delta average**, while F1 = 0 values are included in the F1 average. This asymmetry is by design: delta measures positional accuracy only where detection succeeded, whereas F1 measures detection coverage across all images, including failures.

- **Floating-point representation of shape_weight values** (generated as a range, e.g., 0.9 to 1.9 in steps of 0.1) may introduce small representation artifacts due to IEEE 754 arithmetic. Standard practice is to round shape_weight to one decimal place in the output, ensuring clean values and consistent matching against expected results.

- **Pareto frontier computation operates on full-precision values** for F1 and delta. Rounding is applied afterward for output formatting (typically to 5 decimal places). If rounding is applied before dominance analysis, previously distinct points may become identical, which can alter the frontier composition.

- **The greedy matching algorithm finds the global minimum distance pair at each step**, rather than iterating through centroids in order and assigning each to its nearest available expert. An implementation that processes centroids sequentially may produce different matches than one that always selects the globally closest remaining pair, because the greedy choice at each step affects what remains available for subsequent matches.
