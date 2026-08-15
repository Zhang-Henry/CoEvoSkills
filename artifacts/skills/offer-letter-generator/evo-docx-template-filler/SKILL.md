---
name: evo-docx-template-filler
description: "Fill OOXML (.docx) templates by replacing {{PLACEHOLDER}} tokens with data from a JSON file. Handles placeholders split across XML runs, conditional sections (IF/END_IF blocks), and processes all document parts including headers and footers."
---

# OOXML Template Filler

Fills Word (.docx) templates that use `{{PLACEHOLDER}}` syntax with values from a JSON data file.

## Key Challenges Handled

1. **Split placeholders**: Word may split `{{SOME_VAR}}` across multiple `<w:r>` runs. The skill merges adjacent runs to reconstruct complete placeholders before replacement.
2. **Conditional sections**: `{{IF_RELOCATION}}...{{END_IF_RELOCATION}}` blocks are kept (with markers removed) when the condition is met, or entirely removed when not.
3. **All document parts**: Processes document.xml, headers, and footers.
4. **Validation**: Confirms no unresolved placeholders or conditional markers remain.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-docx-template-filler/scripts')
from utils import fill_template

errors = fill_template(
    template_path='/root/offer_letter_template.docx',
    json_path='/root/employee_data.json',
    output_path='/root/offer_letter_filled.docx'
)

if errors:
    print("Validation errors:")
    for e in errors:
        print(f"  - {e}")
else:
    print("Template filled successfully with no errors.")
```

## Functions

- `load_employee_data(json_path)` - Load JSON data
- `get_xml_parts_to_process(zip_path)` - Find XML parts with potential placeholders
- `merge_split_placeholders(xml_content)` - Merge runs with split placeholders
- `replace_placeholders(xml_bytes, data)` - Replace `{{KEY}}` with values
- `handle_conditional_sections(xml_bytes, data)` - Process IF/END_IF blocks
- `process_template(template_path, output_path, data)` - End-to-end processing
- `validate_output(output_path)` - Check for unresolved placeholders
- `fill_template(template_path, json_path, output_path)` - Main entry point
