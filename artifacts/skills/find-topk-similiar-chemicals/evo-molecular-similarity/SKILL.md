---
name: evo-molecular-similarity
description: "Find top-k similar chemicals from a PDF molecule pool using Morgan fingerprints with Tanimoto similarity. Resolves chemical names to SMILES at runtime via PubChemPy, computes Morgan fingerprints with RDKit, and ranks by Tanimoto similarity with alphabetical tie-breaking."
---

# Molecular Similarity Skill

## Overview
Given a target chemical name and a PDF file listing chemical names (one per line),
this skill identifies the top-k most structurally similar chemicals from the PDF pool.

Pipeline:
1. Extract chemical names from the PDF using pdfplumber
2. Resolve each name to SMILES via PubChemPy at runtime (no manual mapping)
3. Compute Morgan fingerprints via RDKit
4. Compute pairwise Tanimoto similarity between target and each pool molecule
5. Return top-k names sorted by descending similarity, alphabetical tie-breaking

Runtime SMILES lookups are cached to a temp directory keyed by the PDF path hash,
so repeated calls avoid redundant API requests. No pre-built mappings are embedded.

## End-to-End Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-molecular-similarity/scripts')
from utils import topk_tanimoto_similarity_molecules

# Example: find top-k similar molecules from any PDF pool
result = topk_tanimoto_similarity_molecules(
    target_molecule_name="Benzene",       # any chemical name
    molecule_pool_filepath="pool.pdf",    # path to PDF with one name per line
    top_k=5
)
print(result)  # list of up to top_k chemical name strings

# Basic validation
assert isinstance(result, list)
assert len(result) <= 5
assert all(isinstance(n, str) for n in result)
```

## Configuration

The fingerprint parameters are set by the task contract:
- **radius**: 2
- **useChirality**: True
- **nBits**: 2048 (RDKit default for bit-vector Morgan)

These are passed as defaults in `_compute_morgan_fingerprint()` and can be
overridden if a different task contract requires it.

## Key Functions

### `topk_tanimoto_similarity_molecules(target_molecule_name, molecule_pool_filepath, top_k) -> list`
End-to-end entry point. Accepts any target name, any PDF path, and any k.
Returns a list of chemical names from the PDF pool.

### Internal helpers
- `_extract_molecule_names_from_pdf(pdf_path)` — PDF text extraction, one name per line
- `_resolve_name_to_smiles(name)` — PubChem lookup with exponential-backoff retry
- `_build_smiles_lookup(names, cache_path)` — Cached batch resolution with retry passes
- `_compute_morgan_fingerprint(smiles)` — Morgan fingerprint bit-vector
- `_compute_tanimoto(fp1, fp2)` — Tanimoto similarity

## Rate Limiting

PubChem enforces request limits. The skill uses:
- 0.6s delay every 3 requests during initial resolution
- Exponential backoff (1.5s × 2^attempt) on 503 errors
- Two automatic retry passes for any molecules that failed on first attempt
