---
name: evo-doc-organizer
description: "Organize heterogeneous documents (PDF, DOCX, PPTX) into subject-based folders using keyword-based text classification. Use when you need to sort documents into predefined categories based on their content."
---

# Document Organizer Skill

Classifies and organizes documents (PDF, DOCX, PPTX) into subject folders
using keyword-based text extraction and scoring.

## Categories

1. **LLM** - Large Language Models papers
2. **trapped_ion_and_qc** - Trapped ion and quantum computing
3. **black_hole** - Black hole physics
4. **DNA** - DNA-related research
5. **music_history** - Music history and evolution

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-doc-organizer/scripts')
from utils import organize_documents, validate_organization

# Organize all documents from source into category folders
source_dir = '/root/papers/all'
output_dir = '/root/papers'

assignments = organize_documents(source_dir, output_dir)

# Validate the organization
validate_organization(source_dir, output_dir)
```

## Functions

- `extract_text(filepath)` - Extract text from PDF/DOCX/PPTX
- `extract_text_pdf(filepath, max_pages=3)` - Extract from PDF using pdftotext + PyPDF2 fallback
- `extract_text_docx(filepath)` - Extract from DOCX using python-docx
- `extract_text_pptx(filepath)` - Extract from PPTX using python-pptx
- `classify_document(text)` - Classify text into one of 5 categories using weighted keywords
- `organize_documents(source_dir, output_base_dir)` - Full pipeline: extract, classify, copy
- `validate_organization(source_dir, output_base_dir)` - Verify all files organized correctly

## Key Design Decisions

- Uses weighted keyword scoring for robust classification
- Falls back to music_history as the catch-all category
- Copies files (preserves originals) rather than moving
- Validates file count, uniqueness, and size preservation
