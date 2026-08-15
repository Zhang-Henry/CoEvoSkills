import geopandas as gpd
import pandas as pd
import json
from datetime import datetime, timezone
from shapely.ops import unary_union
from shapely.geometry import Point


def load_plate_polygon(plates_path, plate_code="PA"):
    """Load and return the unified polygon geometry for a given plate code."""
    plates = gpd.read_file(plates_path)
    plate = plates[plates["Code"] == plate_code]
    if plate.empty:
        raise ValueError(f"Plate with code '{plate_code}' not found")
    # Union all geometries for this plate into a single geometry
    plate_geom = unary_union(plate.geometry)
    return plate_geom


def load_plate_boundaries(boundaries_path, plate_code="PA"):
    """Load all boundary segments that involve the given plate code.
    Returns a single merged MultiLineString geometry."""
    boundaries = gpd.read_file(boundaries_path)
    # Filter for boundaries containing the plate code in the Name field
    mask = boundaries["Name"].str.contains(plate_code, na=False)
    plate_boundaries = boundaries[mask]
    if plate_boundaries.empty:
        raise ValueError(f"No boundaries found for plate code '{plate_code}'")
    # Merge all boundary LineStrings into a single geometry
    merged = unary_union(plate_boundaries.geometry)
    return merged


def load_earthquakes(earthquakes_path):
    """Load earthquake data from USGS GeoJSON format.
    Returns a GeoDataFrame with proper geometry and CRS."""
    with open(earthquakes_path, 'r') as f:
        data = json.load(f)
    
    features = data['features']
    records = []
    for feat in features:
        props = feat['properties']
        coords = feat['geometry']['coordinates']
        eq_id = feat['id']
        lon, lat = coords[0], coords[1]
        records.append({
            'id': eq_id,
            'mag': props.get('mag'),
            'place': props.get('place'),
            'time_ms': props.get('time'),
            'type': props.get('type'),
            'longitude': lon,
            'latitude': lat,
            'geometry': Point(lon, lat)
        })
    
    gdf = gpd.GeoDataFrame(records, geometry='geometry', crs='EPSG:4326')
    return gdf


def filter_earthquakes_in_plate(earthquakes_gdf, plate_geom):
    """Filter earthquakes to only those within the given plate polygon.
    Uses point-in-polygon test in EPSG:4326."""
    within_mask = earthquakes_gdf.geometry.within(plate_geom)
    filtered = earthquakes_gdf[within_mask].copy()
    return filtered


def compute_distances_to_boundary(earthquakes_gdf, boundary_geom, target_crs="EPSG:4087"):
    """Compute distance from each earthquake to the plate boundary.
    Projects both to a metric CRS (default EPSG:4087) and computes distance in km."""
    # Project earthquakes
    eq_projected = earthquakes_gdf.to_crs(target_crs)
    
    # Project boundary geometry
    boundary_gdf = gpd.GeoDataFrame(geometry=[boundary_geom], crs='EPSG:4326')
    boundary_projected = boundary_gdf.to_crs(target_crs)
    boundary_proj_geom = boundary_projected.geometry.iloc[0]
    
    # Compute distances in meters, convert to km
    distances_m = eq_projected.geometry.distance(boundary_proj_geom)
    distances_km = distances_m / 1000.0
    
    return distances_km


def ms_to_iso8601(time_ms):
    """Convert millisecond Unix timestamp to ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)."""
    time_s = time_ms / 1000.0
    dt = datetime.fromtimestamp(time_s, tz=timezone.utc)
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def find_furthest_earthquake(earthquakes_path, plates_path, boundaries_path, output_path,
                              plate_code="PA", target_crs="EPSG:4087"):
    """End-to-end entry point: find the earthquake furthest from the plate boundary
    within the specified plate. Writes result to output_path as JSON."""
    # Load data
    plate_geom = load_plate_polygon(plates_path, plate_code)
    boundary_geom = load_plate_boundaries(boundaries_path, plate_code)
    earthquakes = load_earthquakes(earthquakes_path)
    
    # Filter to earthquakes within the plate
    eq_in_plate = filter_earthquakes_in_plate(earthquakes, plate_geom)
    print(f"Found {len(eq_in_plate)} earthquakes within plate {plate_code}")
    
    if eq_in_plate.empty:
        raise ValueError(f"No earthquakes found within plate {plate_code}")
    
    # Compute distances
    distances_km = compute_distances_to_boundary(eq_in_plate, boundary_geom, target_crs)
    eq_in_plate = eq_in_plate.copy()
    eq_in_plate['distance_km'] = distances_km.values
    
    # Find the earthquake with maximum distance
    idx_max = eq_in_plate['distance_km'].idxmax()
    furthest = eq_in_plate.loc[idx_max]
    
    # Build result
    result = {
        'id': furthest['id'],
        'place': furthest['place'],
        'time': ms_to_iso8601(furthest['time_ms']),
        'magnitude': furthest['mag'],
        'latitude': furthest['latitude'],
        'longitude': furthest['longitude'],
        'distance_km': round(float(furthest['distance_km']), 2)
    }
    
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"Result written to {output_path}")
    print(json.dumps(result, indent=2))
    return result


def validate_output(output_path):
    """Validate the output JSON file has all required fields and correct types."""
    with open(output_path, 'r') as f:
        result = json.load(f)
    
    required_fields = ['id', 'place', 'time', 'magnitude', 'latitude', 'longitude', 'distance_km']
    for field in required_fields:
        assert field in result, f"Missing required field: {field}"
    
    # Validate types
    assert isinstance(result['id'], str), "id must be a string"
    assert isinstance(result['place'], str), "place must be a string"
    assert isinstance(result['time'], str), "time must be a string"
    assert 'T' in result['time'] and result['time'].endswith('Z'), "time must be ISO 8601 format"
    assert isinstance(result['magnitude'], (int, float)), "magnitude must be numeric"
    assert isinstance(result['latitude'], (int, float)), "latitude must be numeric"
    assert isinstance(result['longitude'], (int, float)), "longitude must be numeric"
    assert isinstance(result['distance_km'], (int, float)), "distance_km must be numeric"
    
    # Validate ranges
    assert -90 <= result['latitude'] <= 90, f"latitude {result['latitude']} out of range"
    assert -180 <= result['longitude'] <= 180, f"longitude {result['longitude']} out of range"
    assert result['distance_km'] > 0, "distance_km must be positive"
    
    print(f"Validation passed for {output_path}")
    return result
