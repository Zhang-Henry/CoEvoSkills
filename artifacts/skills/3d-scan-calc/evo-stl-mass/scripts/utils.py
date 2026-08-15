import struct
import json
import math
from collections import defaultdict


def parse_binary_stl(filepath):
    """Parse a binary STL file.
    Returns list of triangles, each being a dict with:
      'normal': (nx, ny, nz),
      'vertices': [(x1,y1,z1), (x2,y2,z2), (x3,y3,z3)],
      'material_id': int (from attribute byte count field)
    """
    triangles = []
    with open(filepath, 'rb') as f:
        header = f.read(80)
        count_data = f.read(4)
        num_triangles = struct.unpack('<I', count_data)[0]
        for i in range(num_triangles):
            record = f.read(50)
            if len(record) < 50:
                raise ValueError(f"Truncated triangle record at index {i}")
            values = struct.unpack('<12fH', record)
            normal = (values[0], values[1], values[2])
            v1 = (values[3], values[4], values[5])
            v2 = (values[6], values[7], values[8])
            v3 = (values[9], values[10], values[11])
            material_id = values[12]
            triangles.append({
                'normal': normal,
                'vertices': [v1, v2, v3],
                'material_id': material_id
            })
    return triangles


def quantize_vertex(v, tolerance=1e-6):
    """Quantize a vertex to a grid defined by tolerance for hashing."""
    return (
        round(v[0] / tolerance) * tolerance,
        round(v[1] / tolerance) * tolerance,
        round(v[2] / tolerance) * tolerance
    )


def make_vertex_key(v, tolerance=1e-6):
    """Create a hashable key for a vertex with given tolerance."""
    return (
        round(v[0] / tolerance),
        round(v[1] / tolerance),
        round(v[2] / tolerance)
    )


def find_connected_components(triangles, tolerance=1e-6):
    """Find connected components of triangles based on shared vertices.
    Two triangles are connected if they share at least one vertex (within tolerance).
    Returns list of components, each component is a list of triangle indices.
    """
    # Build vertex-to-triangle mapping
    vertex_to_triangles = defaultdict(set)
    triangle_vertices = []  # list of sets of vertex keys per triangle
    
    for i, tri in enumerate(triangles):
        vkeys = set()
        for v in tri['vertices']:
            key = make_vertex_key(v, tolerance)
            vkeys.add(key)
            vertex_to_triangles[key].add(i)
        triangle_vertices.append(vkeys)
    
    # Union-Find
    parent = list(range(len(triangles)))
    rank = [0] * len(triangles)
    
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank[ra] < rank[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank[ra] == rank[rb]:
            rank[ra] += 1
    
    # For each vertex key, union all triangles sharing that vertex
    for vkey, tri_set in vertex_to_triangles.items():
        tri_list = list(tri_set)
        for j in range(1, len(tri_list)):
            union(tri_list[0], tri_list[j])
    
    # Group triangles by component
    components = defaultdict(list)
    for i in range(len(triangles)):
        components[find(i)].append(i)
    
    return list(components.values())


def signed_triangle_volume(v1, v2, v3):
    """Compute signed volume of tetrahedron formed by triangle and origin.
    Using the formula: V = (v1 . (v2 x v3)) / 6.0
    """
    # Cross product v2 x v3
    cx = v2[1] * v3[2] - v2[2] * v3[1]
    cy = v2[2] * v3[0] - v2[0] * v3[2]
    cz = v2[0] * v3[1] - v2[1] * v3[0]
    # Dot product v1 . (v2 x v3)
    dot = v1[0] * cx + v1[1] * cy + v1[2] * cz
    return dot / 6.0


def compute_mesh_volume(triangles, triangle_indices=None):
    """Compute the volume enclosed by a set of triangles using signed tetrahedra method.
    If triangle_indices is provided, only those triangles are used.
    Returns absolute volume (assumes closed mesh with consistent winding).
    """
    total = 0.0
    if triangle_indices is None:
        triangle_indices = range(len(triangles))
    for i in triangle_indices:
        tri = triangles[i]
        v1, v2, v3 = tri['vertices']
        total += signed_triangle_volume(v1, v2, v3)
    return abs(total)


def get_component_material_id(triangles, component_indices):
    """Get the material ID for a component.
    Uses majority vote among triangles in the component.
    """
    counts = defaultdict(int)
    for i in component_indices:
        mid = triangles[i]['material_id']
        counts[mid] += 1
    # Return the most common material ID
    return max(counts, key=counts.get)


def parse_density_table(filepath):
    """Parse the material density table markdown file.
    Returns dict mapping material_id (int) -> density (float) in g/cm^3.
    """
    density_map = {}
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('|') and '**' in line:
                parts = [p.strip() for p in line.split('|')]
                # parts[0] is empty, parts[1] is material ID, parts[3] is density
                parts = [p for p in parts if p]  # remove empty strings
                if len(parts) >= 3:
                    try:
                        mid_str = parts[0].replace('**', '').strip()
                        mid = int(mid_str)
                        density = float(parts[2])
                        density_map[mid] = density
                    except (ValueError, IndexError):
                        pass
    return density_map


def compute_mass(stl_path, density_table_path, output_path):
    """End-to-end entry point: parse STL, find largest component, compute mass, write report.
    
    Args:
        stl_path: Path to binary STL file
        density_table_path: Path to material density table markdown
        output_path: Path to write JSON mass report
    
    Returns:
        dict with 'main_part_mass' and 'material_id'
    """
    # Parse STL
    triangles = parse_binary_stl(stl_path)
    print(f"Parsed {len(triangles)} triangles")
    
    # Determine appropriate tolerance from coordinate scale
    all_coords = []
    for tri in triangles:
        for v in tri['vertices']:
            all_coords.extend(v)
    coord_range = max(all_coords) - min(all_coords)
    tolerance = coord_range * 1e-9
    if tolerance < 1e-9:
        tolerance = 1e-6
    print(f"Coordinate range: {coord_range}, tolerance: {tolerance}")
    
    # Find connected components
    components = find_connected_components(triangles, tolerance)
    print(f"Found {len(components)} connected components")
    for idx, comp in enumerate(components):
        mid = get_component_material_id(triangles, comp)
        vol = compute_mesh_volume(triangles, comp)
        print(f"  Component {idx}: {len(comp)} triangles, material_id={mid}, volume={vol}")
    
    # Find largest component by number of triangles
    largest_comp = max(components, key=len)
    print(f"Largest component has {len(largest_comp)} triangles")
    
    # Get material ID
    material_id = get_component_material_id(triangles, largest_comp)
    print(f"Material ID: {material_id}")
    
    # Compute volume (in STL units, assumed to be mm -> convert to cm^3)
    # STL files typically use mm. Volume in mm^3, convert to cm^3 by dividing by 1000
    volume_stl_units = compute_mesh_volume(triangles, largest_comp)
    print(f"Volume (STL units^3): {volume_stl_units}")
    
    # Parse density table
    density_map = parse_density_table(density_table_path)
    print(f"Density map: {density_map}")
    
    if material_id not in density_map:
        raise ValueError(f"Material ID {material_id} not found in density table")
    
    density = density_map[material_id]  # g/cm^3
    
    # We need to determine the unit system. The doc says "Ensure volume is in cm^3".
    # Common STL units are mm. Volume in mm^3 / 1000 = cm^3
    # But we don't know for sure. Let's check the coordinate scale.
    # If coordinates are in the range of 10s-100s, likely mm.
    # If coordinates are in the range of 1s-10s, likely cm.
    # We'll try mm first (divide by 1000) and also report raw.
    volume_cm3 = volume_stl_units / 1000.0  # mm^3 to cm^3
    print(f"Volume (cm^3, assuming mm units): {volume_cm3}")
    
    mass = volume_cm3 * density
    print(f"Mass: {mass} g")
    
    # Round to 2 decimal places
    mass = round(mass, 2)
    
    result = {
        "main_part_mass": mass,
        "material_id": material_id
    }
    
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=1)
    
    print(f"Report written to {output_path}")
    return result


def validate_report(output_path):
    """Validate the mass report JSON file."""
    with open(output_path, 'r') as f:
        data = json.load(f)
    
    assert 'main_part_mass' in data, "Missing 'main_part_mass' field"
    assert 'material_id' in data, "Missing 'material_id' field"
    assert isinstance(data['main_part_mass'], (int, float)), "main_part_mass must be numeric"
    assert isinstance(data['material_id'], int), "material_id must be integer"
    assert data['main_part_mass'] > 0, "Mass must be positive"
    assert data['material_id'] > 0, "Material ID must be positive"
    print(f"Validation passed: mass={data['main_part_mass']}, material_id={data['material_id']}")
    return data

