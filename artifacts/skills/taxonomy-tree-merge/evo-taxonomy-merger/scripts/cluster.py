"""
Clustering module for hierarchical taxonomy construction.
Uses agglomerative clustering with cosine distance.
"""
import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics.pairwise import cosine_distances
from collections import Counter


def cluster_items(embeddings, n_clusters, min_clusters=3, max_clusters=20):
    """Cluster embeddings into n_clusters groups using agglomerative clustering."""
    n_clusters = max(min_clusters, min(max_clusters, n_clusters, len(embeddings)))
    if len(embeddings) <= n_clusters:
        return list(range(len(embeddings)))
    
    clustering = AgglomerativeClustering(
        n_clusters=n_clusters,
        metric='cosine',
        linkage='average'
    )
    labels = clustering.fit_predict(embeddings)
    return labels.tolist()


def determine_n_clusters(n_items, level, min_c=3, max_c=20):
    """Determine appropriate number of clusters based on item count and level."""
    if level == 1:
        # Top level: 10-20 categories
        return max(10, min(20, int(np.sqrt(n_items / 2))))
    else:
        # Deeper levels: 3-20 subcategories per parent
        if n_items <= 3:
            return n_items
        target = max(3, min(max_c, int(np.sqrt(n_items))))
        return target


def build_hierarchy_recursive(indices, embeddings, norm_levels_list, 
                               current_level, max_level=5,
                               min_children=3, max_children=20):
    """Recursively build hierarchy by clustering at each level.
    
    Args:
        indices: list of indices into the original dataframe
        embeddings: precomputed embeddings matrix (full, indexed by df index)
        norm_levels_list: list of normalized level lists (indexed by df index)
        current_level: current hierarchy level (1-based)
        max_level: maximum depth
        min_children: min children per parent
        max_children: max children per parent
    
    Returns:
        dict mapping index -> list of unified level assignments
    """
    if len(indices) == 0:
        return {}
    
    if current_level > max_level or len(indices) <= 1:
        # Assign all to empty levels for remaining
        result = {}
        for idx in indices:
            result[idx] = [None] * (max_level - current_level + 1)
        return result
    
    # Get embeddings for this subset
    sub_embeddings = embeddings[indices]
    
    # Determine number of clusters
    n_clusters = determine_n_clusters(len(indices), current_level, min_children, max_children)
    
    if len(indices) <= n_clusters:
        # Each item is its own cluster
        labels = list(range(len(indices)))
    else:
        labels = cluster_items(sub_embeddings, n_clusters)
    
    # Group indices by cluster
    clusters = {}
    for i, label in enumerate(labels):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(indices[i])
    
    # Recursively process each cluster
    result = {}
    for cluster_id, cluster_indices in clusters.items():
        # Recurse for next level
        if current_level < max_level and len(cluster_indices) > 1:
            sub_result = build_hierarchy_recursive(
                cluster_indices, embeddings, norm_levels_list,
                current_level + 1, max_level, min_children, max_children
            )
        else:
            sub_result = {}
            for idx in cluster_indices:
                sub_result[idx] = [None] * (max_level - current_level)
        
        for idx in cluster_indices:
            levels_below = sub_result.get(idx, [None] * (max_level - current_level))
            result[idx] = [cluster_id] + levels_below
    
    return result
