---
name: evo-pptx-embedded-update
description: "Surgically update a single cell in an embedded Excel workbook inside a PPTX file, driven by a text-box instruction on the slide. Recalculates cached values for dependent formula cells. Discovers all structure at runtime. Preserves formulas, styles, and package integrity."
---

# Embedded Workbook Update in PPTX

Updates one value cell in an embedded Excel workbook inside a PowerPoint
file. The update instruction is read from a text-box shape on the slide.
All structure (embedded path, worksheet, target cell) is discovered at
runtime. Formula cells are kept as formulas but their cached results
are recalculated to reflect the new value.

## End-to-End Example

The caller sets `input_pptx` and `output_pptx` to the paths given by
the task instruction.

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-pptx-embedded-update/scripts')
from utils import run_end_to_end, validate

input_pptx = '<path from task instruction>'
output_pptx = '<path from task instruction>'

result = run_end_to_end(input_pptx, output_pptx)
validate(output_pptx,
         result['from_currency'],
         result['to_currency'],
         result['new_rate'])
```

## Functions

| Function | Purpose |
|---|---|
| `scan_textboxes(p)` | Collect text from every text-frame shape |
| `parse_update_instruction(t)` | Extract (from, to, value) from free text |
| `locate_embedded_xlsx(p)` | Find the embedded xlsx archive entry |
| `find_matrix_cell(xb, rl, cl)` | Locate a cell by header matching |
| `update_embedded_value(ip, op, fl, tl, v)` | Surgical edit with cache refresh |
| `run_end_to_end(ip, op)` | Full pipeline |
| `validate(op, fl, tl, r)` | Post-hoc integrity check |

## Approach

* **Surgical XML edit** — the target cell's `<v>` text is replaced in
  the raw XML string. Formula cells that transitively depend on the
  changed cell have their cached `<v>` values recalculated.
* **Formula preservation** — `<f>` elements are never removed or
  altered; only `<v>` cached results are refreshed.
* **ZIP preservation** — every other entry in both the xlsx and pptx
  archives is copied with original compression, timestamps, and attrs.
* **Value formats** — user-entered values use `repr()` (shortest
  round-trip decimal); cached formula results use `%.17g` (full
  IEEE 754 precision), matching OOXML conventions.
* **Safe evaluation** — formula evaluation supports ROUND() and basic
  arithmetic via validated expression parsing; unsupported formulas
  leave cached values unchanged.
