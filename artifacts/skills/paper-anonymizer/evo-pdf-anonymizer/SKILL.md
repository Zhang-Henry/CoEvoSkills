---
name: evo-pdf-anonymizer
description: "Anonymize academic PDFs for blind peer review by redacting author names, affiliations, emails, arXiv IDs, venue info, acknowledgement names, and other identity-revealing content using PyMuPDF string-level redaction."
---

# PDF Anonymization Skill

## Overview
Anonymize academic papers by precisely redacting identity-revealing strings while preserving all scientific content. Uses PyMuPDF's search_for + add_redact_annot workflow for true PDF redaction.

## Workflow
1. **Discovery**: Extract text from each PDF page-by-page. Read author blocks, affiliations, emails, acknowledgement sections, headers/footers, and arXiv watermarks. Build an explicit list of strings to redact.
2. **Redaction**: Apply string-level redaction using PyMuPDF. Each redaction targets a specific discovered string.
3. **Verification**: Extract text from the redacted PDF and confirm all target strings are removed, page count preserved, and metadata cleaned.

## Usage

```python
import sys, os
sys.path.insert(0, '/app/environment/skills/evo-pdf-anonymizer/scripts')
from utils import run_anonymization, extract_text, find_references_start_page

# Discover input PDFs at runtime
input_dir = '/path/to/inputs'
output_dir = '/path/to/outputs'
os.makedirs(output_dir, exist_ok=True)

# For each PDF, extract text, read it, and build a redaction list
pages = extract_text(os.path.join(input_dir, 'paper.pdf'))
refs_page = find_references_start_page(pages)

# Build redaction list from discovered content:
# - Read page 0 for author block, affiliations, emails
# - Scan all pages before refs for arXiv IDs, venue headers, GitHub URLs
# - Read acknowledgements section for person names
# - Check PDF metadata for author names
redaction_list = [
    {'text': 'Discovered Author Name', 'pages': 'before_refs'},
    {'text': 'Discovered University', 'pages': 'before_refs'},
    {'text': 'author@university.edu', 'pages': 'all'},
    {'text': 'arXiv:YYMM.NNNNN', 'pages': 'before_refs'},
]

issues = run_anonymization(
    os.path.join(input_dir, 'paper.pdf'),
    os.path.join(output_dir, 'paper.pdf'),
    redaction_list,
    refs_page
)
if issues:
    for issue in issues:
        print(f"WARNING: {issue}")
```

## Redaction List Format
Each entry is a dict with:
- `text`: The exact string to search for and redact
- `pages`: Scope — `'all'` (every page), `'before_refs'` (pages before References section), or a list of 0-based page indices

## Key Rules
- Only redact specific strings via `page.search_for()`, never area-based
- Leave references section untouched (author names in citations stay)
- Redact the paper's own arXiv ID/DOI only before references
- Redact acknowledgement person names but keep surrounding text
- Clean PDF metadata (author field)
- Preserve page count and structure
- Use Unicode-aware search (e.g., curly quotes vs straight quotes)
- Be specific with short strings to avoid false matches in body text
- PyMuPDF search_for is case-insensitive by default — use longer/more specific strings when needed
