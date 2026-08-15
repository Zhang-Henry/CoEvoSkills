"""Validate Civ6 district placement solutions."""
from hex_utils import hex_distance
from map_reader import is_mountain, is_land, is_coast, tile_has_river
from placement import (
    can_place_city, can_place_district, max_specialty_districts,
    build_district_categories
)
from adjacency import evaluate_layout, get_base_district_type

def validate_solution(solution, scenario, map_data, categories=None):
    """Validate a solution dict. Returns list of error strings (empty = valid)."""
    if categories is None:
        categories = build_district_categories()
    
    errors = []
    plots = map_data['plots']
    width = map_data['width']
    wrap_x = map_data['wrap_x']
    num_cities = scenario.get('num_cities', 1)
    population = scenario.get('population', 1)
    max_spec = max_specialty_districts(population)
    specialty_set = categories['specialty']
    no_bonus_set = categories['no_bonus']
    
    # Check required fields
    if num_cities == 1:
        if 'city_center' not in solution:
            errors.append("Missing city_center")
            return errors
        cc = tuple(solution['city_center'])
    else:
        if 'cities' not in solution:
            errors.append("Missing cities")
            return errors
        if len(solution['cities']) != num_cities:
            errors.append(f"Expected {num_cities} cities, got {len(solution['cities'])}")
        cc = tuple(solution['cities'][0]['center'])
    
    if 'placements' not in solution:
        errors.append("Missing placements")
        return errors
    if 'adjacency_bonuses' not in solution:
        errors.append("Missing adjacency_bonuses")
    if 'total_adjacency' not in solution:
        errors.append("Missing total_adjacency")
    
    # Validate city center
    if not can_place_city(cc[0], cc[1], plots):
        errors.append(f"Invalid city center at {cc}")
    
    # Validate placements
    placements = {}
    occupied = {cc}
    spec_count = 0
    
    for dt, pos in solution['placements'].items():
        pos = tuple(pos)
        base = get_base_district_type(dt, no_bonus_set)
        placements[dt] = pos
        
        if pos in occupied:
            errors.append(f"{dt} at {pos} overlaps with another placement")
        occupied.add(pos)
        
        if not can_place_district(pos[0], pos[1], base, cc, occupied - {pos}, map_data):
            errors.append(f"{dt} at {pos} is invalid placement")
        
        if base in specialty_set:
            spec_count += 1
    
    if spec_count > max_spec:
        errors.append(f"Too many specialty districts: {spec_count} > {max_spec}")
    
    # Validate adjacency bonuses
    if 'adjacency_bonuses' in solution:
        total, bonuses = evaluate_layout(cc, placements, map_data, categories)
        
        for dt in placements:
            expected = bonuses.get(dt, 0)
            reported = solution['adjacency_bonuses'].get(dt)
            if reported is None:
                errors.append(f"Missing adjacency bonus for {dt}")
            elif reported != expected:
                errors.append(f"{dt} bonus: reported {reported}, calculated {expected}")
        
        if 'total_adjacency' in solution:
            if solution['total_adjacency'] != total:
                errors.append(f"Total: reported {solution['total_adjacency']}, calculated {total}")
    
    return errors
