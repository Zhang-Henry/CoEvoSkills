---
name: evo-defect-normalizer
description: "Normalize noisy bilingual manufacturing defect reason texts into standardized codebook entries. Derives all categories, keywords, and matching rules from supplied codebook files at runtime. Policy parameters are configurable."
---

# Manufacturing Defect Codebook Normalizer

Normalizes hand-written, noisy, potentially bilingual defect reason texts
from manufacturing test center logs into standardized codebook entries.

## Architecture

All defect categories, keywords, component/net references, and matching
rules are discovered from the supplied codebook files at runtime.

Policy parameters (scoring weights, confidence mapping, thresholds,
separator characters) are exposed as a configuration dict with documented
defaults. See `DEFAULT_CONFIG` in `normalizer.py`.

1. **Codebook Loading**: Parse codebook CSVs, extract metadata
2. **Pattern Building**: Category regex from `keywords_examples`, filtering component/net names
3. **Segmentation**: Split on configurable separators; comma-split only for distinct categories
4. **Bilingual Merging**: Detect same-category CJK/Latin restatements via Unicode ranges
5. **Noise Filtering**: Discard segments lacking any codebook keyword
6. **Matching**: Multi-signal scoring with configurable weights
7. **Confidence**: Continuous mapping with configurable parameters and hash-based jitter
8. **Validation**: Schema, span, code, and confidence coherence checks

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-defect-normalizer/scripts')
from normalizer import normalize_logs
from validator import validate_output

data_dir = '/app/data'
output_path = '/app/output/solution.json'

# Use defaults
records = normalize_logs(data_dir, output_path)

# Or override policy
records = normalize_logs(data_dir, output_path, config={
    'unknown_threshold': 15,
    'conf_min': 0.45,
})

print(f"Processed {len(records)} records")

errors, warnings, stats = validate_output(output_path, data_dir)
print(f"Stats: {stats}")
if not errors:
    print("VALIDATION PASSED")
```

## Scripts

- `scripts/normalizer.py` — Core pipeline with `normalize_logs(data_dir, output_path, config=None)`
- `scripts/validator.py` — Output validator with `validate_output(output_path, data_dir)`
