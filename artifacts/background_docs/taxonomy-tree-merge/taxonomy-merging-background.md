# Taxonomy Merging for Product Category Hierarchies

This document provides background on the principles and techniques involved in merging multiple hierarchical product taxonomies into a single unified classification system, as practiced in e-commerce catalog management and information architecture.

## Why Taxonomies Diverge Across Platforms

Major e-commerce platforms (Amazon, Google Shopping, Facebook/Meta Commerce) each maintain independent product category taxonomies. These taxonomies evolved to serve different business needs: Amazon's browse-node structure emphasizes discoverability for a vast marketplace, Google Shopping's taxonomy is optimized for advertising feed classification, and Facebook's categories support social commerce and catalog-based ad targeting.

As a result, the same real-world concept may live under paths of different
depths and with different labels across platforms. In a deliberately abstract
example, one source may encode `<domain> > <audience> > <item type>` while
another uses `<domain> > <item type> > <use case>`. The semantic content can
overlap even when the structural encoding differs. Cross-platform analytics or
a unified catalog must reconcile those differences into a coherent hierarchy.

## Hierarchical Taxonomy Structure

### Trees, Not Flat Lists

Product taxonomies are rooted trees. Each node represents a category, and the path from the root to a leaf encodes increasing specificity. A path like "Electronics > Computers > Laptops > Gaming Laptops" has depth 4, where each level narrows the scope. The root level contains broad domains (Electronics, Clothing, Home), and deeper levels introduce fine-grained distinctions.

A well-designed taxonomy often exhibits a **pyramid structure**: fewer categories at the top, progressively more below. Appropriate counts depend on the input corpus and any explicit output constraints.

### Depth vs. Breadth Tradeoff

A taxonomy that is too deep forces users through excessive navigation. One that is too broad overwhelms users with choices at each step. Balance depth and breadth using constraints stated by the task and statistics of the source taxonomies. This background intentionally provides no hidden depth, root-count, or child-count target.

When merging taxonomies, this balance must be actively managed. Source taxonomies may have depths of 7 or more levels, so the merged taxonomy may need to truncate or compress deeper paths. Conversely, some source categories may be very shallow and need to be placed at an appropriate depth in the unified tree.

### Prefix Paths and Redundancy

In flat representations of hierarchical data (e.g., CSV files), each row typically encodes a full root-to-node path. This means that for a path "A > B > C", the dataset may also contain "A > B" and "A" as separate rows. When the deeper path exists, the shallower prefix path is redundant -- it carries no additional information because the deeper path already implies the existence of its ancestors. Retaining prefix paths alongside their extensions leads to double-counting and inflated category counts. A clean merge removes prefix paths when a longer extension exists, keeping only the most specific (leaf-level) paths for each branch.

## Text Normalization and Standardization

### Why Normalization Matters

Raw category names from different platforms contain inconsistencies that would cause false distinctions in the merged taxonomy. "Shoes & Boots" and "shoes and boots" are the same category; "Women's Clothing" and "Womens Clothing" differ only by an apostrophe. Without normalization, the merge process treats these as distinct categories, fragmenting what should be unified clusters.

### Case and Punctuation

Converting all text to a consistent case (typically lowercase or title case) eliminates superficial differences. Special characters -- ampersands, slashes, hyphens, apostrophes, commas, parentheses -- should be removed or replaced with spaces. The pipe character "|" is commonly reserved as a word separator in unified category names, so it must not appear in the normalized source text.

### Lemmatization

Lemmatization reduces words to their base (lemma) form: "shoes" becomes "shoe", "running" becomes "run" (or is kept as-is depending on context), "batteries" becomes "battery". This is critical for taxonomy merging because different platforms may use singular vs. plural forms inconsistently. If "Game" and "Games" both appear in category names across the taxonomy, they should be normalized to a single form to avoid confusion and redundant categories.

Standard NLP libraries handle English lemmatization well. The key consideration is to lemmatize individual words within category names rather than treating the entire name as a single token.

### Separator Conventions

Source taxonomies typically use " > " (space-greater than-space) to delimit hierarchy levels in their path representation. The unified taxonomy should adopt a consistent separator convention for category names at each level. If the convention is to use " | " (space-pipe-space) to separate multi-word descriptors within a single category name, this must be applied uniformly and must not be confused with the hierarchy-level separator.

## Clustering Categories Across Sources

### The Core Challenge

The fundamental operation in taxonomy merging is deciding which categories
from different sources should be unified into the same node. Labels can differ
by inflection, word order, abbreviation, or genuine synonymy, so an automated
system needs a principled method to recognize equivalence without relying on a
list copied from the current input.

### Text Similarity and Embeddings

Simple string matching (exact match, Jaccard similarity on word sets) captures obvious overlaps but misses semantic equivalences. "Automobiles" and "Vehicles" share no words but refer to the same domain. Sentence embeddings (from models like Sentence-BERT) map category names into a continuous vector space where semantically similar names are geometrically close. Cosine similarity between embeddings provides a robust similarity measure that captures both lexical and semantic overlap.

### Weighted Level Embeddings

Hierarchical paths can be embedded as a full string, represented level by level, or combined with depth-dependent weights. A level-wise representation makes hierarchy explicit, while a full-path representation is simpler. If weights are used, choose and normalize them from a declared policy or validation; no task-specific decay schedule is supplied here.

### One-Pass Embedding as a Preprocessing Step

Embedding computation is by far the most expensive operation in the taxonomy merging pipeline. For datasets with thousands of categories, computing embeddings takes significant time even with efficient models. The standard practice is to compute **all embeddings exactly once** as a preprocessing step, storing them in a single matrix. All subsequent operations — clustering at every level, centroid computation, nearest-neighbor assignment — operate on subsets of this pre-computed matrix using index arrays, never re-computing embeddings. This is critical for tractability: a pipeline that re-embeds text for each clustering operation or rebalancing step will be orders of magnitude slower and may not complete within practical time limits.

### Hierarchical Clustering

Agglomerative (bottom-up) clustering is a natural fit for taxonomy merging because it directly produces a tree structure. Starting with each category as its own cluster, the algorithm iteratively merges the two most similar clusters until the desired number of top-level groups is reached. The merge history (dendrogram) defines a hierarchy that can be cut at different levels to produce the unified taxonomy's levels.

Key parameters:
- **Linkage criterion** determines how cluster-to-cluster distance is computed. Average linkage uses mean pairwise distances and is robust to outliers, making it a good default for taxonomy merging with cosine distance.
- **Distance metric** is typically cosine distance (1 - cosine similarity) when working with normalized embeddings.
- **Number of clusters** at each level should respect explicit structural constraints and the semantic structure of the data.
- **Cutoff selection**: A dendrogram can be cut by distance, cluster count, stability, or another declared criterion. Do not infer undisclosed target ranges from this background.

### Single-Pass Recursive Construction

A recursive construction can reuse precomputed representations for subsets at each node. Other hierarchical clustering strategies are also possible. Avoid unnecessary re-embedding, but use iterative inspection or repair when it is justified by explicit constraints or observable quality problems; this document does not prescribe the benchmark's reference implementation.

## Naming Unified Categories

### Word-Frequency-Based Name Generation

Category names can be generated from representative member terms, medoids, source labels, or a separately justified naming method. A frequency-based method may weight terms by depth and exclude redundant parent words. Coverage targets, stopword rules, and name-length limits must come from the task instruction or a declared design policy, not from fixed values in this background.

### Representativeness

A unified category's name should be representative of its contents. If a synthetic cluster groups "Laptops", "Desktop Computers", "Tablets", and "Computer Accessories", a concise computing-related name may cover the common theme. Quantify representativeness only when the task defines a measure or when a transparent validation policy is introduced.

**Computing token coverage**: one possible diagnostic extracts normalized name tokens and measures how many member paths contain at least one. Apply the same lemmatization pipeline to names and paths. If a declared coverage criterion is not met, inspect representative terms and rename; no hidden cutoff is supplied here.

### Word Count Constraint

Practical taxonomy names are concise. Follow any explicit word-count and separator requirements; otherwise prefer a short label that identifies the cluster without enumerating all contents.

### Parent-Child Name Independence

A child category's name should not repeat words from its parent's name. If the parent is "Electronics", the child should be "Computers" rather than "Electronic Computers". Repeating the parent's name is redundant because the hierarchy already conveys that relationship. This constraint improves readability and ensures that each level of the hierarchy adds new information.

### Sibling Distinctiveness

Categories at the same level under the same parent should be clearly distinguishable. High word overlap can signal that clustering is too fine-grained or naming is insufficiently specific. Use a declared similarity diagnostic instead of treating an unstated percentage as a benchmark requirement.

## Cross-Source Distribution Balance

### The Problem of Source Dominance

If one source taxonomy is much larger than the others, a naive merge may produce clusters dominated by that source. Measure source representation on the actual inputs before deciding whether correction is needed.

### Source-Exclusive Domains

Some product domains exist only on certain platforms. Source-exclusive domains are not automatically errors: preserve, merge, or place them at another level according to semantic coherence and explicit balance requirements. This background intentionally does not prescribe current category assignments or names.

### Measuring Balance

For each top-level category, source proportions can be computed and summarized. If the task defines a balance constraint, calculate it exactly as stated. Otherwise report the distribution transparently rather than inventing a fixed ratio threshold.

### Techniques for Balancing

Semantic representations can help group related categories across sources. Joint clustering, sampling plus assignment, and post-hoc repair each have tradeoffs in scale, balance, and coherence. Choose a method based on the actual data and explicit constraints; no reference pipeline is supplied here.

## Consistency Between Output Files

A taxonomy merge typically produces two related output artifacts:

1. **A full mapping file** that maps every original source category path to its position in the unified taxonomy (which level-1 category it belongs to, which level-2, etc.). This file preserves the source attribution (which platform the category came from) and the original path.

2. **A hierarchy file** that contains the unique paths in the unified taxonomy itself -- essentially the tree structure without the source mappings. This is a deduplicated projection of the full mapping: every combination of (level_1, level_2, level_3, level_4, level_5) that appears in the full mapping should appear exactly once in the hierarchy file.

The hierarchy file must be a strict subset of the full mapping. Every row in the hierarchy should correspond to at least one row in the full mapping, and the hierarchy should contain no paths that cannot be traced back to at least one source category.

### Structural Integrity

The hierarchy must be a valid tree. This means that if a node exists at level N, all its ancestors at levels 1 through N-1 must also exist. A row with a non-null level_3 but a null level_2 is structurally invalid -- it represents a node floating in the middle of the tree with no parent.

## Key Distinctions in Practice

**Prefix path removal is a standard preprocessing step.** When a source taxonomy contains both "Electronics > Computers" and "Electronics > Computers > Laptops", the shorter path is redundant because the longer one already implies the existence of its ancestor. Standard methodology in taxonomy merging removes these prefix paths during preprocessing, retaining only the most specific (leaf-level) paths for each branch. This prevents inflated category counts and misleading statistics about taxonomy size.

**Consistent lemmatization across all levels ensures accurate normalization.** Lemmatization must be applied uniformly to all category names throughout the taxonomy. Both singular and plural forms of the same word (e.g., "sport" and "sports", or "game" and "games") represent the same concept and should resolve to a single normalized form. Partial or inconsistent application of lemmatization creates false distinctions between what are semantically identical categories.

**Meaningful, human-readable names are required for all categories.** Automated clustering algorithms sometimes produce labels like "Cluster_7", "empty_cluster", or "None" when no clear label can be derived from the cluster contents. These are not valid category names in a production taxonomy. Every category in the output must have a descriptive, human-readable name that conveys the semantic content of its members.

**Thorough character normalization produces a clean, uniform taxonomy.** Source taxonomies contain ampersands ("Shoes & Boots"), slashes ("Arts/Crafts"), hyphens ("T-Shirts"), apostrophes ("Women's"), commas, and parentheses. Complete and consistent normalization of these special characters across all category names is essential for standardization. A mix of cleaned and uncleaned names in the output indicates incomplete normalization.

**Balanced cluster sizes reflect effective organizational structure.** In a well-designed taxonomy, top-level clusters are roughly comparable in size. Extremely large clusters likely warrant further subdivision, while extremely small ones may be better absorbed into related clusters. Wildly varying cluster sizes — one containing thousands of categories while another has only a handful — indicate that the taxonomy does not provide a useful organizational framework.

**Child count enforcement works from deep to shallow.** After initial clustering and naming, some parent nodes will have too many children. The standard post-processing approach is: for each parent with excessive children, sort children by assignment frequency, keep the most frequent ones, and merge the remaining rare children into a descriptive catch-all subcategory. The catch-all name should be derived from representative tokens of the merged group — avoid generic placeholders like "Other" or "Misc" that convey no information and may collide with parent names.

**Child category names introduce new information beyond the parent.** Each level of the hierarchy should add new, distinguishing information. Naming a child "Electronic Devices" under a parent named "Electronics" wastes the child's name budget on information already conveyed by the tree structure. Effective naming ensures that parent and child names are complementary rather than redundant.

**Hierarchy depth can reflect diversity and volume.** Larger or more heterogeneous clusters may benefit from deeper sub-hierarchies, but depth decisions should follow explicit constraints and observable structure rather than copied instance-size examples.

## Standard End-to-End Workflow

The standard methodology for merging product category taxonomies follows these phases in order, with embedding computed exactly once:

**Phase 1 — Preprocessing**: Load all source CSVs. Remove prefix paths (keep only leaf-level paths per source). Clean and lemmatize all category text. Split each path into level columns (level_1 through level_N).

**Phase 2 — Reusable representation**: Compute the selected text representation efficiently and cache it when possible. If combining per-level embeddings, document and justify the weights rather than using a task-specific schedule from background material.

**Phase 3 — Hierarchical construction**: Build the hierarchy with a method appropriate to the representation and constraints. Select clustering, cut, naming, and recursion criteria transparently. Reuse cached representations where possible, and verify parent-child and sibling coherence.

**Phase 4 — Output**: The recursive pass produces a unified level assignment for every source category. Write the full mapping CSV (source, category_path, depth, unified_level_1 through unified_level_5). Derive the hierarchy CSV by deduplicating the unified level columns from the full mapping. No row expansion is needed — the hierarchy is simply the unique combinations of (level_1, ..., level_5) that appear in the full mapping.
