---
name: evo-stl-mass
description: "Parse binary STL files with material IDs in attribute bytes, find largest connected component, compute volume and mass. Use when calculating mass of 3D printed parts from STL scan data."
---

# STL Mass Calculation Skill

This skill parses binary STL files where the 2-byte attribute field stores a Material ID,
finds the largest connected component (filtering out debris), computes the enclosed volume
using signed tetrahedra, and calculates mass using a material density lookup table.

## Quick Start

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-stl-mass/scripts')
from utils import compute_mass, validate_report

result = compute_mass(
    stl_path='/root/scan_data.stl',
    density_table_path='/root/material_density_table.md',
    output_path='/root/mass_report.json'
)
print(result)

validate_report('/root/mass_report.json')
```

## Key Functions

- `parse_binary_stl(filepath)` - Parse binary STL, extract triangles with material IDs
- `find_connected_components(triangles, tolerance)` - Union-Find based component detection
- `compute_mesh_volume(triangles, indices)` - Signed tetrahedra volume calculation
- `get_component_material_id(triangles, indices)` - Majority vote material ID
- `parse_density_table(filepath)` - Parse markdown density table
- `compute_mass(stl_path, density_table_path, output_path)` - End-to-end entry point
- `validate_report(output_path)` - Validate output JSON

## Algorithm

1. Parse binary STL: 80-byte header + 4-byte count + N*50-byte records
2. Each record: 12 floats (normal + 3 vertices) + 2-byte attribute (Material ID)
3. Build vertex adjacency with tolerance-based matching
4. Union-Find to group connected triangles
5. Select largest component by triangle count
6. Compute volume via signed tetrahedra sum
7. Convert units (mm^3 to cm^3 if needed)
8. Look up density and compute mass
