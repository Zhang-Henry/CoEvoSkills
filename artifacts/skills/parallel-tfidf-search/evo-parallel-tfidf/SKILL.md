---
name: evo-parallel-tfidf
description: "Parallelize a sequential TF-IDF search engine using Python multiprocessing. Covers parallel index building (tokenization, TF, DF, IDF, inverted index, doc vectors) and parallel batch query search. Produces identical results to sequential with 1.5x+ indexing and 2x+ search speedup on 4 workers."
---

# Parallel TF-IDF Search Engine Skill

## Overview

This skill parallelizes a sequential TF-IDF document search engine using Python's `multiprocessing.Pool`. The key design decisions:

1. **Two-phase index building**: Phase 1 parallelizes tokenization/TF/DF computation. Phase 2 parallelizes inverted index + doc vector construction using global IDF.
2. **Minimized serialization**: Each worker gets only its document chunk + the shared IDF dict (not all doc data).
3. **Initializer-based search workers**: The index is sent once via `Pool(initializer=...)` rather than per-query.
4. **Batched queries**: Queries are grouped into batches for amortized IPC cost.

## Key Architecture

### Index Building Strategy
- Split documents into chunks (respecting `chunk_size` param, but ensuring >= num_workers chunks)
- Phase 1 workers: tokenize docs, compute TF, compute local DF counts
- Main process: merge DFs, compute global IDF
- Phase 2 workers: given their doc TFs + global IDF, compute partial inverted index + doc vectors + norms
- Main process: merge partial inverted indices, sort posting lists

### Search Strategy  
- Use `Pool(initializer=_init_search_worker, initargs=(index, documents))` to send index once
- Split queries into batches (num_workers * 4 for load balancing)
- Each worker processes its batch using the sequential `search_sequential` function
- Reassemble results by query index

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-parallel-tfidf/scripts')
from parallel_tfidf import build_tfidf_index_parallel, batch_search_parallel, ParallelIndexingResult

# Also need sequential module in path
sys.path.insert(0, '/root/workspace')
from document_generator import generate_corpus

# Generate or load documents
documents = generate_corpus(5000, seed=42)

# Build index in parallel
result = build_tfidf_index_parallel(documents, num_workers=4, chunk_size=500)
print(f"Built index in {result.elapsed_time:.3f}s")

# Search in parallel
queries = ["machine learning", "data analysis"]
results, elapsed = batch_search_parallel(queries, result.index, top_k=10, num_workers=4, documents=documents)
print(f"Search completed in {elapsed:.3f}s")
for i, query_results in enumerate(results):
    print(f"Query '{queries[i]}': {len(query_results)} results")
```

## Correctness Invariants
- Vocabulary, document_frequencies, idf dicts must be identical to sequential
- Inverted index posting lists must contain same (doc_id, score) pairs (order may differ for equal scores)
- Doc vectors and norms must match within floating point tolerance
- Search results must match sequential for same index and queries

## Performance Notes
- Index building speedup depends on corpus size; overhead dominates for <1000 docs
- Search speedup depends on number of queries; overhead dominates for <50 queries
- With 4 workers on 5000 docs: ~2.5x index speedup, ~3x search speedup
- Chunk size tuning: smaller chunks = better load balance but more IPC overhead
