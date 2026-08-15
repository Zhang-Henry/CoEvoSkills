"""End-to-end entry point for Civ6 district adjacency optimization."""
import json
import os
import sys

def resolve_map_path(scenario_path, map_file):
    """Resolve map file path relative to scenario or /data."""
    scenario_dir = os.path.dirname(os.path.abspath(scenario_path))
    data_dir = os.path.dirname(scenario_dir)  # parent of scenario dir
    for candidate in [
        os.path.join(scenario_dir, map_file),
        os.path.join(data_dir, map_file),
        map_file
    ]:
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(f"Map file not found: {map_file}")

def solve_scenario(scenario_path, output_path):
    """Solve a Civ6 adjacency optimization scenario.
    
    Args:
        scenario_path: Path to scenario.json
        output_path: Path to write solution JSON
    """
    with open(scenario_path) as f:
        scenario = json.load(f)
    
    map_file = scenario.get('map_file', '')
    map_path = resolve_map_path(scenario_path, map_file)
    num_cities = scenario.get('num_cities', 1)
    population = scenario.get('population', 1)
    
    from map_reader import read_map
    from optimizer import optimize_scenario
    from placement import build_district_categories
    
    map_data = read_map(map_path)
    categories = build_district_categories()
    
    print(f"Map: {map_data['width']}x{map_data['height']}, WrapX={map_data['wrap_x']}")
    
    result = optimize_scenario(map_data, num_cities, population, categories)
    
    print(f"Best CC: {result['city_center']}, Total: {result['total']}")
    print(f"Placements: {result['placements']}")
    print(f"Bonuses: {result['bonuses']}")
    
    cc = result['city_center']
    placements = result['placements']
    bonuses = result['bonuses']
    
    placements_out = {dt: list(pos) for dt, pos in placements.items()}
    adj_out = {dt: bonuses[dt] for dt in placements}
    
    if num_cities == 1:
        output = {
            'city_center': list(cc),
            'placements': placements_out,
            'adjacency_bonuses': adj_out,
            'total_adjacency': result['total']
        }
    else:
        output = {
            'cities': [{'center': list(cc)}],
            'placements': placements_out,
            'adjacency_bonuses': adj_out,
            'total_adjacency': result['total']
        }
    
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"Written to {output_path}")
    print(json.dumps(output, indent=2))
    return output

def validate_output(output_path, scenario_path):
    """Validate the output file against scenario constraints."""
    from validator import validate_solution
    from map_reader import read_map
    
    with open(scenario_path) as f:
        scenario = json.load(f)
    with open(output_path) as f:
        solution = json.load(f)
    
    map_file = scenario.get('map_file', '')
    map_path = resolve_map_path(scenario_path, map_file)
    map_data = read_map(map_path)
    
    errors = validate_solution(solution, scenario, map_data)
    if errors:
        print("VALIDATION ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return False
    else:
        print("VALIDATION PASSED")
        return True

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: python main.py <scenario_path> <output_path>")
        sys.exit(1)
    solve_scenario(sys.argv[1], sys.argv[2])
    validate_output(sys.argv[2], sys.argv[1])
