---
name: evo-latex-formula-extraction
description: "Extract display-mode LaTeX formulas from PDF research papers. Use when the task requires identifying all display-mode (own-line) formulas from a PDF, extracting them as LaTeX, cleaning tags/punctuation, detecting bracket mismatches and misspelled commands, and outputting original + fixed formulas in markdown format."
---

# LaTeX Formula Extraction from PDF

This skill extracts display-mode LaTeX formulas from PDF research papers, cleans them, validates bracket matching, and produces a markdown output file.

## Workflow

1. **Extract**: Use marker-pdf to convert PDF to markdown (preserves LaTeX formulas)
2. **Detect**: Use surya layout detection to find equation bounding boxes
3. **Cross-reference**: Use texify on cropped equation regions for verification
4. **Clean**: Remove `\tag{}`, trailing equation numbers, trailing commas/periods
5. **Validate**: Check bracket matching (`\left`/`\right` pairs) and command spelling
6. **Fix**: Generate corrected versions for formulas with syntax errors
7. **Output**: Write original formulas followed by fixed versions

## Key Functions

- `extract_formulas_with_marker(pdf_path, output_dir)` - Extract formulas via marker-pdf
- `detect_equation_bboxes(pdf_path)` - Find equation regions using surya layout
- `extract_formulas_with_texify(pdf_path, bboxes)` - Extract formulas from cropped regions
- `clean_formula(formula)` - Remove tags, numbers, punctuation
- `validate_brackets(formula)` - Check \left/\right delimiter matching
- `fix_bracket_mismatches(formula)` - Fix mismatched delimiter pairs
- `check_misspelled_commands(formula)` - Detect misspelled LaTeX commands
- `run_extraction_pipeline(pdf_path, output_path)` - End-to-end entry point
- `validate_output(output_path)` - Validate output file format

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-latex-formula-extraction/scripts')
from utils import run_extraction_pipeline, validate_output

# Run the full pipeline
pdf_path = '/root/latex_paper.pdf'
output_path = '/root/latex_formula_extraction.md'

original, fixed = run_extraction_pipeline(pdf_path, output_path)

# Validate the output
validate_output(output_path)
```

## Important Notes

- Only display-mode formulas (on their own line) are extracted, not inline math
- Bracket validation covers: `()`, `[]`, `\{\}`, `\langle\rangle`, `|`, `\|`
- Fix only syntax/typographical errors, never mathematical content
- Original erroneous formulas are kept; fixed versions are appended after all originals
- Deduplication is applied to avoid repeated formulas
