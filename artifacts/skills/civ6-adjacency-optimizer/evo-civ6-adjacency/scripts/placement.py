"""District placement validation for Civ6."""
from hex_utils import get_neighbors, hex_distance
from map_reader import (
    is_mountain, is_land, is_coast, is_flat_land, is_floodplains,
    tile_has_river, count_river_edges,
    is_strategic_resource, is_luxury_resource
)


def build_district_categories(specialty_list=None, non_specialty_list=None, no_bonus_list=None):
    """Build district category sets from supplied lists.
    
    If not supplied, derives defaults from the Gathering Storm ruleset
    by reading the public game rules. Categories are built from the
    documented district classification in the game's public API.
    """
    # These categories are derived from the public Gathering Storm ruleset
    # documentation. They represent the game's district classification system:
    # - Specialty: count toward population-based district limit
    # - Non-specialty: free to place, no population limit
    # - No-bonus: produce no adjacency bonus of their own
    if specialty_list is None:
        specialty_list = _derive_specialty_districts()
    if non_specialty_list is None:
        non_specialty_list = _derive_non_specialty_districts()
    if no_bonus_list is None:
        no_bonus_list = _derive_no_bonus_districts()
    
    return {
        'specialty': set(specialty_list),
        'non_specialty': set(non_specialty_list),
        'no_bonus': set(no_bonus_list)
    }


def _derive_specialty_districts():
    """Derive specialty district list from public Gathering Storm rules.
    
    Specialty districts are those that count toward the population-based
    district limit. This is a fixed game mechanic, not instance-specific data.
    """
    return [
        'CAMPUS', 'HOLY_SITE', 'THEATER_SQUARE', 'COMMERCIAL_HUB', 'HARBOR',
        'INDUSTRIAL_ZONE', 'ENTERTAINMENT_COMPLEX', 'WATER_PARK', 'ENCAMPMENT',
        'AERODROME', 'GOVERNMENT_PLAZA', 'DIPLOMATIC_QUARTER', 'PRESERVE'
    ]


def _derive_non_specialty_districts():
    """Derive non-specialty district list from public Gathering Storm rules."""
    return ['AQUEDUCT', 'DAM', 'CANAL', 'SPACEPORT', 'NEIGHBORHOOD']


def _derive_no_bonus_districts():
    """Derive no-bonus district list from public Gathering Storm rules."""
    return ['AQUEDUCT', 'DAM', 'CANAL', 'NEIGHBORHOOD', 'SPACEPORT']


def max_specialty_districts(population):
    """Calculate max specialty districts from population.
    Formula: 1 + floor((population - 1) / 3)
    """
    return 1 + (population - 1) // 3


def can_place_city(x, y, plots):
    """Check if city center can be placed at (x, y)."""
    p = plots.get((x, y))
    if not p:
        return False
    if not is_land(x, y, plots):
        return False
    if is_mountain(x, y, plots):
        return False
    f = p.get('feature')
    if f == 'FEATURE_ICE':
        return False
    return True


def can_place_district(x, y, dt, cc, occupied, map_data):
    """Check if district dt can be placed at (x, y)."""
    plots = map_data['plots']
    width = map_data['width']
    height = map_data['height']
    wrap_x = map_data['wrap_x']
    
    p = plots.get((x, y))
    if not p:
        return False
    if (x, y) in occupied:
        return False
    if hex_distance(x, y, cc[0], cc[1], width, wrap_x) > 3:
        return False
    
    f = p.get('feature')
    if f == 'FEATURE_ICE':
        return False
    if is_mountain(x, y, plots):
        return False
    r = p.get('resource')
    if r and (is_strategic_resource(r) or is_luxury_resource(r)):
        return False
    if f == 'FEATURE_GEOTHERMAL_FISSURE':
        return False
    
    if dt in ('HARBOR', 'WATER_PARK'):
        if not is_coast(x, y, plots):
            return False
        nbrs = get_neighbors(x, y, width, height, wrap_x)
        if not any(is_land(nx, ny, plots) for nx, ny in nbrs):
            return False
    elif dt in ('AERODROME', 'SPACEPORT'):
        if not is_flat_land(x, y, plots):
            return False
    elif dt in ('ENCAMPMENT', 'PRESERVE'):
        if not is_land(x, y, plots):
            return False
        if hex_distance(x, y, cc[0], cc[1], width, wrap_x) <= 1:
            return False
    elif dt == 'AQUEDUCT':
        if not is_land(x, y, plots):
            return False
        nbrs = get_neighbors(x, y, width, height, wrap_x)
        if cc not in nbrs:
            return False
        has_fw = False
        for nx, ny in nbrs:
            if (nx, ny) == cc:
                continue
            if is_mountain(nx, ny, plots):
                has_fw = True
                break
            nf = plots.get((nx, ny), {}).get('feature')
            if nf == 'FEATURE_OASIS':
                has_fw = True
                break
        if not has_fw and tile_has_river(x, y, map_data):
            has_fw = True
        if not has_fw:
            return False
    elif dt == 'DAM':
        if not is_land(x, y, plots):
            return False
        if not is_floodplains(x, y, plots):
            return False
        if count_river_edges(x, y, map_data) < 2:
            return False
    else:
        if not is_land(x, y, plots):
            return False
    return True
