---
name: evo-earthquake-distance
description: "Find the earthquake furthest from a tectonic plate boundary within that plate. Uses GeoPandas for spatial containment and distance computation with EPSG:4087 projection."
---

# Earthquake Distance to Plate Boundary Analysis

This skill finds the earthquake that occurred furthest from a tectonic plate boundary within the plate itself, using GeoPandas projections.

## Workflow

1. Load plate polygon geometry from PB2002_plates.json
2. Load all boundary segments for the plate from PB2002_boundaries.json
3. Load earthquake data from USGS GeoJSON format
4. Filter earthquakes to those within the plate polygon (point-in-polygon in EPSG:4326)
5. Project both earthquake points and boundary geometry to EPSG:4087 (equidistant cylindrical)
6. Compute minimum distance from each earthquake to the merged boundary
7. Find the earthquake with maximum distance
8. Output result as JSON with required fields

## Usage Example

```python
import sys
sys.path.insert(0, '/app/environment/skills/evo-earthquake-distance/scripts')
from utils import find_furthest_earthquake, validate_output

# Run end-to-end analysis
result = find_furthest_earthquake(
    earthquakes_path='/root/earthquakes_2024.json',
    plates_path='/root/PB2002_plates.json',
    boundaries_path='/root/PB2002_boundaries.json',
    output_path='/root/answer.json',
    plate_code='PA',
    target_crs='EPSG:4087'
)

# Validate output
validate_output('/root/answer.json')
```

## Key Design Decisions

- **EPSG:4087** (World Equidistant Cylindrical) is used for distance computation as it provides reasonable distance accuracy across the entire Pacific plate
- **Point-in-polygon** testing is done in EPSG:4326 to avoid projection distortion at plate edges
- **All boundary segments** containing the plate code are included (not just one neighbor)
- **Time conversion**: USGS timestamps are in milliseconds, divided by 1000 before conversion to ISO 8601
- **Pacific plate** is a MultiPolygon due to antimeridian crossing; handled automatically by GeoPandas

## Utility Functions

- `load_plate_polygon(plates_path, plate_code)` - Load unified plate polygon
- `load_plate_boundaries(boundaries_path, plate_code)` - Load merged boundary geometry
- `load_earthquakes(earthquakes_path)` - Load earthquakes as GeoDataFrame
- `filter_earthquakes_in_plate(earthquakes_gdf, plate_geom)` - Spatial filter
- `compute_distances_to_boundary(earthquakes_gdf, boundary_geom, target_crs)` - Distance computation
- `ms_to_iso8601(time_ms)` - Timestamp conversion
- `find_furthest_earthquake(...)` - End-to-end entry point
- `validate_output(output_path)` - Output validation
