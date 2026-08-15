---
name: evo-pptx-dangling-titles
description: "Detect and process dangling paper titles in PPTX presentations. Reformats text boxes with paper titles (font, size, color), repositions them to bottom center, and creates a reference slide with auto-numbered unique titles."
---

# Dangling Paper Title Processor for PPTX

## Overview
This skill processes PowerPoint presentations to find "dangling paper titles" - text boxes
(non-placeholder shapes) containing paper title text. It reformats them, repositions them,
and creates a summary reference slide.

## What are Dangling Paper Titles?
In academic presentation slides, paper titles are often placed as free-floating text boxes
(not in standard placeholders like Title or Content). These are detected by finding
non-placeholder shapes with text frames that contain text.

## Operations
1. **Detect**: Find all TEXT_BOX shapes (non-placeholders) with text content
2. **Reformat**: Change font to Arial, size 16pt, color #989596, disable bold
3. **Resize**: Adjust box width so title displays in one line
4. **Reposition**: Center horizontally at bottom of slide
5. **Reference Slide**: Create new slide with "Reference" title and auto-numbered unique titles

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-pptx-dangling-titles/scripts')
from utils import process_pptx, validate_output

# Process the PPTX
result = process_pptx('/root/Awesome-Agent-Papers.pptx', '/root/Awesome-Agent-Papers_processed.pptx')

# Validate the output
errors = validate_output('/root/Awesome-Agent-Papers_processed.pptx')
if errors:
    print("VALIDATION FAILED")
else:
    print("ALL CHECKS PASSED")
```

## Key Functions

- `detect_dangling_titles(prs)` - Returns list of dicts with slide_index, shape, text
- `estimate_text_width_emu(text, font_size_pt, font_name)` - Estimates EMU width for single-line text
- `format_dangling_title(shape, slide_width, slide_height)` - Applies formatting and positioning
- `collect_unique_titles(dangling_items)` - Deduplicates titles preserving order
- `create_reference_slide(prs, titles)` - Creates reference slide with numbered list
- `process_pptx(input_path, output_path)` - End-to-end entry point
- `validate_output(output_path)` - Validates the processed file
