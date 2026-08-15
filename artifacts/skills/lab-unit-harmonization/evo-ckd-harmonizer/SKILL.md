---
name: evo-ckd-harmonizer
description: "Harmonize clinical lab data with mixed units to US conventional units. Detects bimodal distributions from mixed unit systems, applies molecular-weight-based conversions, handles comma decimals and scientific notation."
---

# Clinical Lab Data Unit Harmonizer

Harmonizes clinical laboratory data from multiple healthcare systems that may
use different units for the same analyte (e.g., SI vs US conventional).

## Procedure

1. **Load & parse**: read CSV as strings, fix comma-decimal and scientific notation
2. **Drop incomplete rows**: remove rows with any missing values
3. **Build analyte registry**: a built-in registry maps common clinical analytes to
   their US conventional unit, known alternative units, molecular weights, and
   conversion factors. Each entry includes a physiological plausibility range
   used to detect which values are in the alternative unit.
4. **Runtime column matching**: each input column name is matched against the
   registry using normalized name matching (case-insensitive, underscore/space
   tolerant, common abbreviation expansion)
5. **Bimodal detection**: for matched columns, a log-space gap analysis identifies
   whether the column contains a mixture of two unit populations
6. **Apply conversions**: values outside the expected US range are converted using
   the registry factor; values already in the US range are left unchanged
7. **Round & format**: all numeric values rounded to 2 decimal places as `X.XX`
8. **Save**: write harmonized CSV

## Example (synthetic)

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-ckd-harmonizer/scripts')
from utils import harmonize, validate

# Run end-to-end: reads input, drops missing, converts units, formats, saves
df = harmonize(
    input_path='/path/to/raw_lab_data.csv',
    output_path='/path/to/harmonized_output.csv'
)

# Validate output format and ranges
valid = validate('/path/to/harmonized_output.csv')
```

## Analyte Registry Design

The registry is a list of entries, each containing:
- canonical analyte name patterns (regex or keyword list)
- US conventional unit and expected physiological range
- one or more alternative units with conversion direction and factor
- factors derived from molecular weight, SI prefix ratios, or physical constants

At runtime, each data column is matched to a registry entry. If no match is
found, the column is left unchanged. If a match is found, values outside the
US range are converted. Multi-group columns (e.g., three distinct unit
populations) are handled by applying multiple conversion rules in sequence.

## Key Principles

- Conversion factors come from molecular weights and SI prefix ratios
- Threshold detection uses log-space gap analysis, not hardcoded boundaries
- The registry is general clinical chemistry knowledge, not dataset-specific
- Column-to-analyte matching happens at runtime from column names
- Round only the final output, convert at full precision
