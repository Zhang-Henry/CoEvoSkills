---
name: evo-taxonomy-merger
description: "Merge product category taxonomies from multiple e-commerce platforms (Amazon, Facebook, Google Shopping) into a unified 5-level hierarchy. Use when you need to unify category systems across platforms with text normalization, embedding-based clustering, and constraint-validated naming."
---

# Taxonomy Merger Skill

Merges hierarchical product category taxonomies from multiple e-commerce platforms into a single unified 5-level taxonomy.

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-taxonomy-merger/scripts')
from pipeline import run_pipeline
from validate import print_validation_report

# Run the full pipeline
full_df, hier_df = run_pipeline(
    data_dir='/root/data',
    output_dir='/root/output',
    max_levels=5,
    top_min=10,
    top_max=20,
    child_min=3,
    child_max=20
)

# Validate output
passed = print_validation_report(
    '/root/output/unified_taxonomy_full.csv',
    '/root/output/unified_taxonomy_hierarchy.csv'
)
print(f"Validation passed: {passed}")
```

## Pipeline Phases

1. **Preprocess** (`preprocess.py`): Load CSVs, remove prefix paths, normalize text, lemmatize
2. **Embed** (`embed.py`): Compute sentence embeddings once using sentence-transformers
3. **Cluster & Name** (`pipeline.py`): Hierarchical agglomerative clustering at each level with word-frequency naming
4. **Validate** (`validate.py`): Check all constraints (category counts, naming rules, overlaps, distribution)

## Key Constraints Enforced

- 10-20 top-level categories
- 3-20 subcategories per parent at deeper levels
- Category names use " | " separator, max 5 words
- 70%+ representativeness coverage
- No parent-child name overlap
- <30% word overlap between siblings
- Balanced cluster sizes and even source distribution

## Module Reference

### preprocess.py
- `load_sources(data_dir)` - Load and tag source CSVs
- `remove_prefix_paths(df)` - Remove redundant prefix paths
- `preprocess_dataframe(df)` - Add normalized columns
- `normalize_and_lemmatize(text)` - Full text normalization

### embed.py
- `compute_embeddings(texts, model_name, batch_size)` - Compute sentence embeddings

### pipeline.py
- `run_pipeline(data_dir, output_dir, ...)` - End-to-end entry point
- `hierarchical_cluster_and_name(df, embeddings, ...)` - Build hierarchy

### validate.py
- `validate_full_output(full_path, hier_path)` - Check all constraints
- `print_validation_report(full_path, hier_path)` - Print report
