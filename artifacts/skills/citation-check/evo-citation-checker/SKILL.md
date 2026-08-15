---
name: evo-citation-checker
description: "Verify academic BibTeX citations to identify fake/hallucinated references using DOI resolution, CrossRef API, Semantic Scholar, DBLP provenance analysis, and structural red flag detection. Use when asked to check bibliography integrity."
---

# Citation Verification Skill

Identifies fake/hallucinated citations in BibTeX files using multi-signal verification.

## Verification Strategy

1. **DOI-first triage**: Check DOIs via CrossRef API and doi.org resolution
2. **Provenance signals**: DBLP biburl/bibsource and ACL Anthology URLs indicate real entries
3. **DOI registrant analysis**: Suspicious prefixes like 10.1234, 10.5678 indicate fabrication
4. **Semantic Scholar search**: For entries without DOIs, search by title
5. **Red flag analysis**: Generic titles, fake journal names, metadata inconsistencies

## Key Fake Citation Indicators

- DOI returns 404 from CrossRef AND doi.org
- DOI registrant code is a placeholder (10.1234, 10.5678, etc.)
- Journal/venue name doesn't exist in any index
- Publisher attribution is wrong for the claimed venue
- Generic/vague title + generic author names + no provenance

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-citation-checker/scripts')
from utils import verify_citations, validate_answer

# Run end-to-end verification
answer, details = verify_citations('/root/test.bib', '/root/answer.json')
print(answer)

# Validate output
validate_answer('/root/answer.json')
```

## Scripts

- `scripts/utils.py`: All utility functions including:
  - `parse_bib_file(path)` - Parse BibTeX
  - `clean_bibtex_title(title)` - Remove BibTeX formatting
  - `check_doi_crossref(doi)` - Verify DOI via CrossRef
  - `check_doi_resolution(doi)` - Verify DOI via doi.org
  - `search_semantic_scholar(title)` - Search S2 by title
  - `has_dblp_provenance(entry)` - Check DBLP provenance
  - `has_acl_anthology_url(entry)` - Check ACL Anthology URL
  - `is_suspicious_doi_prefix(doi)` - Check for fake DOI prefixes
  - `analyze_entry_suspicion(entry)` - Score suspicion signals
  - `verify_citations(bib_path, output_path)` - End-to-end entry point
  - `validate_answer(output_path)` - Validate output format
