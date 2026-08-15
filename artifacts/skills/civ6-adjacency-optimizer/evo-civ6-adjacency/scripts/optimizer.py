"""Greedy optimizer for Civ6 district placement."""
from hex_utils import get_neighbors, hex_distance, tiles_within_range
from map_reader import (
    is_mountain, is_land, is_coast, is_flat_land, is_floodplains,
    tile_has_river, is_strategic_resource
)
from placement import (
    can_place_city, can_place_district, max_specialty_districts,
    build_district_categories
)
from adjacency import evaluate_layout, get_base_district_type


def derive_spec_priority(categories):
    """Derive specialty district priority from categories at runtime.
    
    Orders specialty districts by their typical adjacency potential
    based on the public adjacency rules: districts with major bonuses
    from map features (mountains, geothermal, reefs, rivers) are
    prioritized over those that depend on improvements or wonders.
    """
    # Districts that can get major bonuses from map features
    high_value = ['CAMPUS', 'INDUSTRIAL_ZONE', 'COMMERCIAL_HUB', 'HOLY_SITE', 'HARBOR']
    # Districts with lower map-feature adjacency potential
    medium_value = ['THEATER_SQUARE', 'ENTERTAINMENT_COMPLEX']
    # Remaining specialty districts
    remaining = [d for d in categories['specialty']
                 if d not in high_value and d not in medium_value]
    
    result = []
    for d in high_value + medium_value + remaining:
        if d in categories['specialty']:
            result.append(d)
    return result


def derive_nonspec_priority(categories):
    """Derive non-specialty district priority from categories at runtime.
    
    Orders non-specialty districts by adjacency-boosting potential:
    Aqueduct/Dam give IZ +2 each, Neighborhood is a generic filler.
    """
    # Districts that provide specific major bonuses to neighbors
    boosters = ['AQUEDUCT', 'DAM', 'CANAL']
    # Generic filler districts
    fillers = ['NEIGHBORHOOD']
    remaining = [d for d in categories['non_specialty']
                 if d not in boosters and d not in fillers]
    
    result = []
    for d in boosters + fillers + remaining:
        if d in categories['non_specialty']:
            result.append(d)
    return result


def find_interesting_area(map_data):
    """Find tiles with high-value features for adjacency."""
    plots = map_data['plots']
    interesting = []
    for (x, y), p in plots.items():
        f = p.get('feature', '')
        if f == 'FEATURE_ICE': continue
        t = p['terrain']
        if 'OCEAN' in t: continue
        score = 0
        if 'MOUNTAIN' in t: score += 2
        if f == 'FEATURE_GEOTHERMAL_FISSURE': score += 4
        if f == 'FEATURE_REEF': score += 4
        if f and 'FLOODPLAINS' in f: score += 2
        if tile_has_river(x, y, map_data) and is_land(x, y, plots): score += 1
        if score > 0 or is_land(x, y, plots):
            interesting.append((x, y, score))
    return interesting


def compute_search_breadth(map_data):
    """Derive search breadth from map size at runtime.
    
    Scales candidate count with map dimensions to balance
    thoroughness vs computation time.
    """
    total_tiles = map_data['width'] * map_data['height']
    plots = map_data['plots']
    land_count = sum(1 for p in plots.values()
                     if 'COAST' not in p['terrain'] and 'OCEAN' not in p['terrain'])
    # Use fraction of land tiles, with minimum and maximum bounds
    breadth = max(10, min(land_count, int(total_tiles ** 0.5)))
    return breadth


def find_city_candidates(map_data, interesting_tiles):
    """Find promising city center locations."""
    plots = map_data['plots']
    width = map_data['width']
    wrap_x = map_data['wrap_x']
    candidates = []
    for (x, y) in plots:
        if not can_place_city(x, y, plots): continue
        score = 0
        for ix, iy, iscore in interesting_tiles:
            d = hex_distance(x, y, ix, iy, width, wrap_x)
            if d <= 3: score += iscore
        if score > 0:
            candidates.append((x, y, score))
    candidates.sort(key=lambda c: -c[2])
    breadth = compute_search_breadth(map_data)
    return [(c[0], c[1]) for c in candidates[:breadth]]


def greedy_optimize(cc, map_data, max_spec, categories=None,
                    spec_priority=None, nonspec_priority=None,
                    max_iterations=12):
    """Greedy district placement with multiple neighborhood support."""
    if categories is None:
        categories = build_district_categories()
    if spec_priority is None:
        spec_priority = derive_spec_priority(categories)
    if nonspec_priority is None:
        nonspec_priority = derive_nonspec_priority(categories)
    
    no_bonus = categories['no_bonus']
    plots = map_data['plots']
    width = map_data['width']
    wrap_x = map_data['wrap_x']
    tiles_r3 = tiles_within_range(cc[0], cc[1], 3, plots, width, wrap_x)
    
    placed = {}
    occupied = {cc}
    spec_count = 0
    
    for iteration in range(max_iterations):
        best_gain = 0
        best_dt = None
        best_pos = None
        best_is_spec = False
        current_total = evaluate_layout(cc, placed, map_data, categories)[0] if placed else 0
        
        district_options = []
        if spec_count < max_spec:
            for sdt in spec_priority:
                if sdt not in placed:
                    district_options.append((sdt, True))
        for ndt in nonspec_priority:
            if ndt == 'NEIGHBORHOOD':
                nh_idx = sum(1 for k in placed if k.startswith('NEIGHBORHOOD'))
                key = f'NEIGHBORHOOD_{nh_idx}' if nh_idx > 0 else 'NEIGHBORHOOD'
                district_options.append((key, False))
            elif ndt not in placed:
                district_options.append((ndt, False))
        
        for dt_key, is_spec in district_options:
            dt_actual = get_base_district_type(dt_key, no_bonus)
            for tx, ty in tiles_r3:
                if (tx, ty) in occupied: continue
                if not can_place_district(tx, ty, dt_actual, cc, occupied, map_data): continue
                test_p = dict(placed)
                test_p[dt_key] = (tx, ty)
                score, _ = evaluate_layout(cc, test_p, map_data, categories)
                gain = score - current_total
                if gain > best_gain:
                    best_gain = gain
                    best_dt = dt_key
                    best_pos = (tx, ty)
                    best_is_spec = is_spec
        
        if best_dt is None or best_gain <= 0:
            break
        placed[best_dt] = best_pos
        occupied.add(best_pos)
        if best_is_spec:
            spec_count += 1
    
    return placed


def optimize_scenario(map_data, num_cities, population, categories=None):
    """Main optimization entry point."""
    if categories is None:
        categories = build_district_categories()
    max_spec = max_specialty_districts(population)
    interesting = find_interesting_area(map_data)
    city_candidates = find_city_candidates(map_data, interesting)
    
    if not city_candidates:
        plots = map_data['plots']
        city_candidates = [(x, y) for (x, y) in plots if can_place_city(x, y, plots)]
    
    best_total = -1
    best_cc = None
    best_placements = None
    best_bonuses = None
    
    for cc in city_candidates:
        placed = greedy_optimize(cc, map_data, max_spec, categories)
        total, bonuses = evaluate_layout(cc, placed, map_data, categories)
        if total > best_total:
            best_total = total
            best_cc = cc
            best_placements = dict(placed)
            best_bonuses = dict(bonuses)
    
    return {
        'city_center': best_cc,
        'placements': best_placements,
        'bonuses': best_bonuses,
        'total': best_total
    }
