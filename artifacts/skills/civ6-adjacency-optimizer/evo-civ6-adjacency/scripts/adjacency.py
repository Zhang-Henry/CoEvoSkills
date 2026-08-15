"""Adjacency bonus calculation for Civ6 districts."""
from hex_utils import get_neighbors
from map_reader import is_mountain, is_coast, tile_has_river, is_strategic_resource
from placement import build_district_categories

# Build default categories once
_DEFAULT_CATS = build_district_categories()

def get_base_district_type(dt, no_bonus_set=None):
    """Normalize indexed district names like NEIGHBORHOOD_2 to base type."""
    if no_bonus_set is None:
        no_bonus_set = _DEFAULT_CATS['no_bonus']
    for base in no_bonus_set:
        if dt.startswith(base):
            return base
    return dt

def get_effective_features(all_placements, plots):
    """Compute features after district placement destroys forests/jungles/marshes."""
    eff = {}
    for pos, p in plots.items():
        eff[pos] = p['feature']
    for dt, pos in all_placements.items():
        if dt == 'CITY_CENTER':
            continue
        f = eff.get(pos)
        if f in ('FEATURE_FOREST', 'FEATURE_JUNGLE', 'FEATURE_MARSH'):
            eff[pos] = None
    return eff

def compute_adjacency(dt, x, y, all_placements, eff, map_data, categories=None):
    """Compute adjacency bonus for a single district."""
    if categories is None:
        categories = _DEFAULT_CATS
    no_bonus = categories['no_bonus']
    
    plots = map_data['plots']
    width = map_data['width']
    height = map_data['height']
    wrap_x = map_data['wrap_x']
    
    base = get_base_district_type(dt, no_bonus)
    if base in no_bonus:
        return 0
    
    nbrs = get_neighbors(x, y, width, height, wrap_x)
    
    adj_count = 0
    adj_types = {}
    for nx, ny in nbrs:
        for pdt, ppos in all_placements.items():
            if ppos == (nx, ny):
                adj_count += 1
                adj_types[(nx, ny)] = get_base_district_type(pdt, no_bonus)
                break
    
    bonus = 0
    
    if base == 'CAMPUS':
        for nx, ny in nbrs:
            ef = eff.get((nx, ny))
            if ef == 'FEATURE_GEOTHERMAL_FISSURE': bonus += 2
            if ef == 'FEATURE_REEF': bonus += 2
            if is_mountain(nx, ny, plots): bonus += 1
        jungle_c = sum(1 for nx, ny in nbrs if eff.get((nx, ny)) == 'FEATURE_JUNGLE')
        bonus += jungle_c // 2
        bonus += adj_count // 2
    elif base == 'HOLY_SITE':
        for nx, ny in nbrs:
            if is_mountain(nx, ny, plots): bonus += 1
        forest_c = sum(1 for nx, ny in nbrs if eff.get((nx, ny)) == 'FEATURE_FOREST')
        bonus += forest_c // 2
        bonus += adj_count // 2
    elif base == 'COMMERCIAL_HUB':
        if tile_has_river(x, y, map_data): bonus += 2
        for nx, ny in nbrs:
            if adj_types.get((nx, ny)) == 'HARBOR': bonus += 2
        bonus += adj_count // 2
    elif base == 'INDUSTRIAL_ZONE':
        for nx, ny in nbrs:
            adt = adj_types.get((nx, ny), '')
            if adt in ('AQUEDUCT', 'DAM', 'CANAL'): bonus += 2
            r = plots.get((nx, ny), {}).get('resource')
            if is_strategic_resource(r): bonus += 1
        bonus += adj_count // 2
    elif base == 'HARBOR':
        for nx, ny in nbrs:
            if adj_types.get((nx, ny)) == 'CITY_CENTER': bonus += 2
            if is_coast(nx, ny, plots) and plots.get((nx, ny), {}).get('resource'): bonus += 1
        bonus += adj_count // 2
    elif base == 'THEATER_SQUARE':
        for nx, ny in nbrs:
            adt = adj_types.get((nx, ny), '')
            if adt in ('ENTERTAINMENT_COMPLEX', 'WATER_PARK'): bonus += 2
        bonus += adj_count // 2
    else:
        bonus += adj_count // 2
    
    return bonus

def evaluate_layout(cc, placements, map_data, categories=None):
    """Evaluate total adjacency for a complete layout."""
    if categories is None:
        categories = _DEFAULT_CATS
    plots = map_data['plots']
    all_p = {'CITY_CENTER': cc}
    all_p.update(placements)
    eff = get_effective_features(all_p, plots)
    total = 0
    bonuses = {}
    for dt, pos in placements.items():
        b = compute_adjacency(dt, pos[0], pos[1], all_p, eff, map_data, categories)
        bonuses[dt] = b
        total += b
    return total, bonuses
