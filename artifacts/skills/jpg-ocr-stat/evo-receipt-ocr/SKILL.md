---
name: evo-receipt-ocr
description: "Extract dates and total amounts from scanned receipt images using OCR and write results to Excel. Use when processing receipt images for data extraction."
---

# Receipt OCR Extraction Skill

Extracts dates and total monetary amounts from scanned receipt images using Tesseract OCR.

## Usage

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-receipt-ocr/scripts')
from utils import process_all_receipts, validate_output

# Process all receipts
results = process_all_receipts('/app/workspace/dataset/img', '/app/workspace/stat_ocr.xlsx')

# Validate output
validate_output('/app/workspace/stat_ocr.xlsx')
```

## Key Functions

- `preprocess_image(img)` - Apply multiple preprocessing strategies
- `ocr_image(image_path)` - Run OCR with multiple configs
- `extract_date(texts)` - Extract date in ISO format
- `extract_total_amount(texts)` - Extract total using keyword priority
- `process_receipt(image_path)` - Process single receipt
- `process_all_receipts(image_dir, output_path)` - End-to-end pipeline
- `validate_output(output_path)` - Validate Excel output
