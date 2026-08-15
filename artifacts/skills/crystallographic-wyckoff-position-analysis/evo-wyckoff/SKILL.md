---
name: evo-wyckoff
description: "Analyze CIF files for Wyckoff position multiplicities and approximate fractional coordinates. Use when a task requires parsing crystallographic CIF files, determining Wyckoff positions via symmetry analysis, and outputting multiplicity counts and rational coordinate strings."
---

# Wyckoff Position Analysis Skill

Analyzes crystal structure CIF files to determine Wyckoff position multiplicities
and approximate fractional coordinates for the first atom of each Wyckoff position.

## Dependencies

- pymatgen (for CIF parsing and SpacegroupAnalyzer)
- spglib (used internally by pymatgen for symmetry detection)
- Python standard library: fractions

## Key Functions

### `analyze_wyckoff_position_multiplicities_and_coordinates(filepath)`
Main entry point. Parses a CIF file, determines Wyckoff positions, and returns
multiplicities and coordinates as rational fraction strings (denominator ≤ 12).

### `float_to_frac_str(val, max_denom=12)`
Converts a float to a rational string with bounded denominator.

### `coords_to_frac_strs(coords, max_denom=12)`
Converts an array of 3 coordinates to fraction strings.

### `validate_result(result, filepath)`
Validates output structure, key consistency, total atom count, and fraction format.

## Algorithm

1. Parse CIF file with pymatgen Structure.from_file()
2. Run SpacegroupAnalyzer to detect symmetry and Wyckoff letters
3. Group atoms by Wyckoff letter, summing counts for multiplicity
4. For each unique letter, take the first atom's original fractional coordinates
5. Convert coordinates to rational fractions with denominator ≤ 12

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-wyckoff/scripts')
from utils import analyze_wyckoff_position_multiplicities_and_coordinates, validate_result

# Analyze a CIF file
filepath = '/root/cif_files/FeS2_mp-226.cif'
result = analyze_wyckoff_position_multiplicities_and_coordinates(filepath)
print(result)

# Validate the result
validate_result(result, filepath)
```

## Writing solution.py

The task requires writing the function at /root/workspace/solution.py:

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-wyckoff/scripts')
from utils import analyze_wyckoff_position_multiplicities_and_coordinates

# The function is directly importable and usable
# Example: result = analyze_wyckoff_position_multiplicities_and_coordinates('/root/cif_files/FeS2_mp-226.cif')
```
