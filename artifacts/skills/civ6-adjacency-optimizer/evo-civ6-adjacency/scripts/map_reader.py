"""Read Civ6Map SQLite database and extract map data."""
import sqlite3

def read_map(map_path):
    """Read a .Civ6Map file and return structured map data."""
    conn = sqlite3.connect(map_path)
    cursor = conn.cursor()
    
    # Map dimensions
    cursor.execute("SELECT Width, Height, WrapX, WrapY FROM Map")
    width, height, wrap_x, wrap_y = cursor.fetchone()
    
    # Plots
    cursor.execute("SELECT ID, TerrainType, IsImpassable FROM Plots")
    plots = {}
    for pid, terrain, imp in cursor.fetchall():
        x, y = pid % width, pid // width
        plots[(x, y)] = {
            'terrain': terrain,
            'impassable': imp,
            'feature': None,
            'resource': None,
            'rivers': {'IsNEOfRiver': 0, 'IsWOfRiver': 0, 'IsNWOfRiver': 0}
        }
    
    # Features
    cursor.execute("SELECT ID, FeatureType FROM PlotFeatures")
    for pid, ftype in cursor.fetchall():
        x, y = pid % width, pid // width
        if (x, y) in plots:
            plots[(x, y)]['feature'] = ftype
    
    # Resources
    cursor.execute("SELECT ID, ResourceType, ResourceCount FROM PlotResources")
    for pid, rtype, rcount in cursor.fetchall():
        x, y = pid % width, pid // width
        if (x, y) in plots:
            plots[(x, y)]['resource'] = rtype
    
    # Rivers
    cursor.execute("SELECT ID, IsNEOfRiver, IsWOfRiver, IsNWOfRiver FROM PlotRivers")
    for pid, ne, w, nw in cursor.fetchall():
        x, y = pid % width, pid // width
        if (x, y) in plots:
            plots[(x, y)]['rivers'] = {'IsNEOfRiver': ne, 'IsWOfRiver': w, 'IsNWOfRiver': nw}
    
    conn.close()
    
    return {
        'width': width,
        'height': height,
        'wrap_x': bool(wrap_x),
        'wrap_y': bool(wrap_y),
        'plots': plots
    }

def tile_has_river(x, y, map_data):
    """Check if tile has any river edge touching it."""
    plots = map_data['plots']
    width = map_data['width']
    wrap_x = map_data['wrap_x']
    p = plots.get((x, y))
    if not p:
        return False
    r = p['rivers']
    if r['IsNEOfRiver'] or r['IsWOfRiver'] or r['IsNWOfRiver']:
        return True
    # Check complementary edges from neighbors
    def get_plot(nx, ny):
        if wrap_x:
            nx = nx % width
        return plots.get((nx, ny))
    if y % 2 == 0:
        e = get_plot(x + 1, y)
        if e and e['rivers']['IsWOfRiver']: return True
        sw = get_plot(x - 1, y + 1)
        if sw and sw['rivers']['IsNEOfRiver']: return True
        se = get_plot(x, y + 1)
        if se and se['rivers']['IsNWOfRiver']: return True
    else:
        e = get_plot(x + 1, y)
        if e and e['rivers']['IsWOfRiver']: return True
        sw = get_plot(x, y + 1)
        if sw and sw['rivers']['IsNEOfRiver']: return True
        se = get_plot(x + 1, y + 1)
        if se and se['rivers']['IsNWOfRiver']: return True
    return False

def count_river_edges(x, y, map_data):
    """Count how many river edges touch this tile."""
    plots = map_data['plots']
    width = map_data['width']
    wrap_x = map_data['wrap_x']
    p = plots.get((x, y))
    if not p:
        return 0
    count = 0
    r = p['rivers']
    if r['IsNEOfRiver']: count += 1
    if r['IsWOfRiver']: count += 1
    if r['IsNWOfRiver']: count += 1
    def get_plot(nx, ny):
        if wrap_x:
            nx = nx % width
        return plots.get((nx, ny))
    if y % 2 == 0:
        e = get_plot(x + 1, y)
        if e and e['rivers']['IsWOfRiver']: count += 1
        sw = get_plot(x - 1, y + 1)
        if sw and sw['rivers']['IsNEOfRiver']: count += 1
        se = get_plot(x, y + 1)
        if se and se['rivers']['IsNWOfRiver']: count += 1
    else:
        e = get_plot(x + 1, y)
        if e and e['rivers']['IsWOfRiver']: count += 1
        sw = get_plot(x, y + 1)
        if sw and sw['rivers']['IsNEOfRiver']: count += 1
        se = get_plot(x + 1, y + 1)
        if se and se['rivers']['IsNWOfRiver']: count += 1
    return count

# Terrain helpers
def is_mountain(x, y, plots):
    p = plots.get((x, y))
    return p is not None and 'MOUNTAIN' in p['terrain']

def is_land(x, y, plots):
    p = plots.get((x, y))
    return p is not None and 'COAST' not in p['terrain'] and 'OCEAN' not in p['terrain']

def is_coast(x, y, plots):
    p = plots.get((x, y))
    return p is not None and 'COAST' in p['terrain']

def is_flat_land(x, y, plots):
    p = plots.get((x, y))
    if not p:
        return False
    t = p['terrain']
    return 'COAST' not in t and 'OCEAN' not in t and 'HILLS' not in t and 'MOUNTAIN' not in t

def is_floodplains(x, y, plots):
    p = plots.get((x, y))
    if not p:
        return False
    f = p.get('feature')
    return f is not None and 'FLOODPLAINS' in f



def classify_resource(resource_type):
    """Classify a resource type at runtime from its name pattern.
    
    Civ6 resource naming convention:
    - Strategic resources contain keywords like HORSES, IRON, NITER, COAL, OIL, ALUMINUM, URANIUM
    - Bonus resources contain keywords like RICE, WHEAT, DEER, FISH, STONE, SHEEP, CATTLE, BANANAS, COPPER, MAIZE, CRABS
    - All other RESOURCE_ prefixed types are luxury resources
    
    Returns: 'strategic', 'bonus', or 'luxury'
    """
    if not resource_type or not resource_type.startswith('RESOURCE_'):
        return None
    name = resource_type.upper()
    # Strategic resources are those with military/industrial significance
    strategic_keywords = {'HORSES', 'IRON', 'NITER', 'COAL', 'OIL', 'ALUMINUM', 'URANIUM'}
    # Bonus resources provide food/production but cannot be traded
    bonus_keywords = {'RICE', 'WHEAT', 'DEER', 'FISH', 'STONE', 'SHEEP', 'CATTLE', 
                      'BANANAS', 'COPPER', 'MAIZE', 'CRABS'}
    suffix = name.replace('RESOURCE_', '')
    if suffix in strategic_keywords:
        return 'strategic'
    if suffix in bonus_keywords:
        return 'bonus'
    return 'luxury'

def is_strategic_resource(resource_type):
    """Check if resource is strategic at runtime."""
    return classify_resource(resource_type) == 'strategic'

def is_luxury_resource(resource_type):
    """Check if resource is luxury at runtime."""
    return classify_resource(resource_type) == 'luxury'

def is_bonus_resource(resource_type):
    """Check if resource is bonus at runtime."""
    return classify_resource(resource_type) == 'bonus'

def discover_resources_from_map(map_path):
    """Discover and classify all resources present in a map file."""
    import sqlite3
    conn = sqlite3.connect(map_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT ResourceType FROM PlotResources")
    resources = {}
    for (rtype,) in cursor.fetchall():
        resources[rtype] = classify_resource(rtype)
    conn.close()
    return resources
