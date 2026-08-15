#!/usr/bin/env python3
"""
Parallel TF-IDF Implementation

Parallel version of the TF-IDF search engine using multiprocessing.
Optimized to minimize serialization overhead and maximize parallelism.
"""

import math
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from heapq import nlargest
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sequential import (
    STOP_WORDS,
    TOKEN_PATTERN,
    SearchResult,
    TFIDFIndex,
    tokenize,
    compute_term_frequencies,
    search_sequential,
)
from document_generator import Document


@dataclass
class ParallelIndexingResult:
    """Result from parallel index building."""
    index: TFIDFIndex
    elapsed_time: float
    num_documents: int
    vocabulary_size: int


# ============================================================================
# Worker Functions for Index Building  
# ============================================================================

def _process_and_build_chunk(args):
    """
    Phase 1: Process a chunk of documents - tokenize, compute TF.
    Returns per-document TF dicts and per-term document counts.
    """
    chunk = args  # list of (doc_id, title, content)
    doc_tfs = []  # list of (doc_id, tf_dict)
    local_df = defaultdict(int)  # term -> count of docs containing it in this chunk
    
    for doc_id, title, content in chunk:
        text = title + " " + content
        tokens = tokenize(text)
        tf = compute_term_frequencies(tokens)
        doc_tfs.append((doc_id, tf))
        for term in tf:
            local_df[term] += 1
    
    return doc_tfs, dict(local_df)


def _build_vectors_and_postings(args):
    """
    Phase 2: Given doc TFs and global IDF, compute:
    - Partial inverted index entries for these docs
    - Doc vectors and norms
    """
    doc_tfs, idf_dict = args
    
    partial_inverted = defaultdict(list)  # term -> [(doc_id, tfidf)]
    doc_vectors = {}  # doc_id -> {term: tfidf}
    doc_norms = {}    # doc_id -> norm
    
    for doc_id, tf_dict in doc_tfs:
        doc_vector = {}
        norm_squared = 0.0
        for term, tf in tf_dict.items():
            idf_val = idf_dict[term]
            tfidf = tf * idf_val
            doc_vector[term] = tfidf
            norm_squared += tfidf * tfidf
            partial_inverted[term].append((doc_id, tfidf))
        doc_vectors[doc_id] = doc_vector
        doc_norms[doc_id] = math.sqrt(norm_squared)
    
    return dict(partial_inverted), doc_vectors, doc_norms


# ============================================================================
# Parallel Index Building
# ============================================================================

def build_tfidf_index_parallel(documents, num_workers=None, chunk_size=500):
    """
    Build TF-IDF inverted index in parallel using multiprocessing.
    """
    start_time = time.perf_counter()
    
    if num_workers is None:
        num_workers = os.cpu_count() or 4
    
    index = TFIDFIndex()
    index.num_documents = len(documents)
    
    if not documents:
        elapsed = time.perf_counter() - start_time
        return ParallelIndexingResult(
            index=index, elapsed_time=elapsed,
            num_documents=0, vocabulary_size=0
        )
    
    # Prepare lightweight tuples
    doc_data = [(doc.doc_id, doc.title, doc.content) for doc in documents]
    
    # Split into chunks - use chunk_size parameter
    chunks = [doc_data[i:i + chunk_size] for i in range(0, len(doc_data), chunk_size)]
    # Ensure we have enough chunks for parallelism
    if len(chunks) < num_workers:
        actual_chunk_size = max(len(doc_data) // num_workers, 1)
        chunks = [doc_data[i:i + actual_chunk_size] for i in range(0, len(doc_data), actual_chunk_size)]
    
    # Phase 1: Parallel tokenization and TF computation
    with Pool(processes=num_workers) as pool:
        phase1_results = pool.map(_process_and_build_chunk, chunks)
    
    # Merge Phase 1 results: collect all doc TFs and aggregate DFs
    all_doc_tfs = []  # flat list of (doc_id, tf_dict)
    global_df = defaultdict(int)
    
    for doc_tfs, local_df in phase1_results:
        all_doc_tfs.extend(doc_tfs)
        for term, count in local_df.items():
            global_df[term] += count
    
    index.document_frequencies = dict(global_df)
    index.vocabulary = set(global_df.keys())
    
    # Compute IDF (fast, sequential)
    N = index.num_documents
    idf_dict = {}
    for term, df in global_df.items():
        idf_dict[term] = math.log(N / df) + 1
    index.idf = idf_dict
    
    # Phase 2: Parallel computation of inverted index + doc vectors
    # Re-chunk the doc TFs for phase 2
    p2_chunk_size = max(len(all_doc_tfs) // (num_workers * 2), 1)
    p2_chunks = [all_doc_tfs[i:i + p2_chunk_size] 
                 for i in range(0, len(all_doc_tfs), p2_chunk_size)]
    
    p2_args = [(chunk, idf_dict) for chunk in p2_chunks]
    
    with Pool(processes=num_workers) as pool:
        phase2_results = pool.map(_build_vectors_and_postings, p2_args)
    
    # Merge Phase 2 results
    merged_inverted = defaultdict(list)
    for partial_inv, partial_vecs, partial_norms in phase2_results:
        for term, postings in partial_inv.items():
            merged_inverted[term].extend(postings)
        index.doc_vectors.update(partial_vecs)
        index.doc_norms.update(partial_norms)
    
    # Sort posting lists by score descending (to match sequential)
    for term in merged_inverted:
        merged_inverted[term].sort(key=lambda x: x[1], reverse=True)
    
    index.inverted_index = dict(merged_inverted)
    
    elapsed = time.perf_counter() - start_time
    
    return ParallelIndexingResult(
        index=index, elapsed_time=elapsed,
        num_documents=len(documents),
        vocabulary_size=len(index.vocabulary)
    )


# ============================================================================
# Worker Functions for Search
# ============================================================================

_worker_index = None
_worker_documents = None


def _init_search_worker(index_data, doc_data):
    """Initialize worker with shared index data."""
    global _worker_index, _worker_documents
    _worker_index = index_data
    _worker_documents = doc_data


def _search_query_batch(query_batch):
    """
    Process a batch of (query_idx, query_str, top_k) tuples.
    """
    global _worker_index, _worker_documents
    results = []
    for query_idx, query_str, top_k in query_batch:
        res = search_sequential(query_str, _worker_index, top_k, _worker_documents)
        results.append((query_idx, res))
    return results


# ============================================================================
# Parallel Search
# ============================================================================

def batch_search_parallel(queries, index, top_k=10, num_workers=None, documents=None):
    """
    Search for multiple queries in parallel using multiprocessing.
    
    Returns:
        Tuple of (List[List[SearchResult]], elapsed_time)
    """
    start_time = time.perf_counter()
    
    if num_workers is None:
        num_workers = os.cpu_count() or 4
    
    if not queries:
        elapsed = time.perf_counter() - start_time
        return [], elapsed
    
    # Prepare query work items with indices to maintain order
    query_items = [(i, q, top_k) for i, q in enumerate(queries)]
    
    # Split queries into batches - enough for good load balancing
    num_batches = num_workers * 4
    batch_size = max(len(query_items) // num_batches, 1)
    query_batches = [query_items[i:i + batch_size] 
                     for i in range(0, len(query_items), batch_size)]
    
    # Use initializer to send index to workers once
    with Pool(
        processes=num_workers,
        initializer=_init_search_worker,
        initargs=(index, documents)
    ) as pool:
        batch_results = pool.map(_search_query_batch, query_batches)
    
    # Reassemble results in original query order
    all_results = [None] * len(queries)
    for batch in batch_results:
        for query_idx, results in batch:
            all_results[query_idx] = results
    
    elapsed = time.perf_counter() - start_time
    
    return all_results, elapsed


if __name__ == "__main__":
    from document_generator import generate_corpus
    from sequential import build_tfidf_index_sequential, batch_search_sequential
    
    print("=" * 60)
    print("Parallel TF-IDF Search Engine - Test")
    print("=" * 60)
    
    # Use larger corpus for meaningful performance testing
    num_docs = 5000
    print(f"\nGenerating {num_docs} document corpus...")
    documents = generate_corpus(num_docs, seed=42)
    
    # Test parallel index building
    print("\nBuilding index (sequential)...")
    seq_result = build_tfidf_index_sequential(documents)
    print(f"Sequential: {seq_result.elapsed_time:.3f}s")
    
    for nw in [4]:
        print(f"\nBuilding index (parallel, {nw} workers)...")
        par_result = build_tfidf_index_parallel(documents, num_workers=nw)
        print(f"Parallel: {par_result.elapsed_time:.3f}s")
        print(f"Speedup: {seq_result.elapsed_time / par_result.elapsed_time:.2f}x")
    
    # Verify correctness
    seq_idx = seq_result.index
    par_idx = par_result.index
    
    print(f"\nVocabulary match: {seq_idx.vocabulary == par_idx.vocabulary}")
    print(f"Doc freq match: {seq_idx.document_frequencies == par_idx.document_frequencies}")
    print(f"IDF match: {seq_idx.idf == par_idx.idf}")
    
    inv_match = True
    for term in seq_idx.inverted_index:
        seq_postings = sorted(seq_idx.inverted_index[term])
        par_postings = sorted(par_idx.inverted_index.get(term, []))
        if seq_postings != par_postings:
            inv_match = False
            break
    print(f"Inverted index match: {inv_match}")
    
    vec_match = all(
        seq_idx.doc_vectors[did] == par_idx.doc_vectors.get(did, {})
        for did in seq_idx.doc_vectors
    )
    print(f"Doc vectors match: {vec_match}")
    
    norm_match = all(
        abs(seq_idx.doc_norms[did] - par_idx.doc_norms.get(did, 0)) < 1e-10
        for did in seq_idx.doc_norms
    )
    print(f"Doc norms match: {norm_match}")
    
    # Test parallel search
    test_queries = [
        "machine learning algorithm",
        "data analysis",
        "network security",
        "software development",
        "artificial intelligence",
        "cloud computing infrastructure",
        "database optimization",
        "web application framework",
        "operating system kernel",
        "distributed computing",
    ] * 50  # 500 queries
    
    print(f"\nSearching {len(test_queries)} queries...")
    
    search_start = time.perf_counter()
    seq_search_results = batch_search_sequential(test_queries, seq_idx, top_k=10, documents=documents)
    seq_search_time = time.perf_counter() - search_start
    print(f"Sequential search: {seq_search_time:.3f}s")
    
    par_search_results, par_search_time = batch_search_parallel(
        test_queries, par_idx, top_k=10, num_workers=4, documents=documents
    )
    print(f"Parallel search: {par_search_time:.3f}s")
    print(f"Search speedup: {seq_search_time / par_search_time:.2f}x")
    
    # Verify search results match
    search_match = True
    for i in range(len(test_queries)):
        seq_res = seq_search_results[i]
        par_res = par_search_results[i]
        if len(seq_res) != len(par_res):
            search_match = False
            print(f"Query {i}: length mismatch {len(seq_res)} vs {len(par_res)}")
            break
        for s, p in zip(seq_res, par_res):
            if s.doc_id != p.doc_id or abs(s.score - p.score) > 1e-10:
                search_match = False
                print(f"Query {i}: result mismatch")
                break
        if not search_match:
            break
    print(f"Search results match: {search_match}")
