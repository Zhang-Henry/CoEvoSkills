"""Hex grid utilities for Civ6 odd-r offset coordinate system."""

def get_neighbors(x, y, width, height, wrap_x=False):
    """Get 6 hex neighbors using odd-r offset coordinates."""
    if y % 2 == 0:
        offsets = [(1,0),(0,-1),(-1,-1),(-1,0),(-1,1),(0,1)]
    else:
        offsets = [(1,0),(1,-1),(0,-1),(-1,0),(0,1),(1,1)]
    result = []
    for dx, dy in offsets:
        nx, ny = x + dx, y + dy
        if wrap_x:
            nx = nx % width
        if 0 <= nx < width and 0 <= ny < height:
            result.append((nx, ny))
    return result

def hex_distance(x1, y1, x2, y2, width=0, wrap_x=False):
    """Compute hex distance using cube coordinates."""
    def to_cube(x, y):
        cx = x - (y - (y & 1)) // 2
        cz = y
        return cx, -cx - cz, cz
    best = float('inf')
    offsets = [-width, 0, width] if wrap_x and width > 0 else [0]
    for wo in offsets:
        c1 = to_cube(x1 + wo, y1)
        c2 = to_cube(x2, y2)
        d = max(abs(c1[0]-c2[0]), abs(c1[1]-c2[1]), abs(c1[2]-c2[2]))
        best = min(best, d)
    return best

def tiles_within_range(cx, cy, r, plots, width, wrap_x):
    """Get all tile positions within hex distance r of (cx, cy)."""
    return [pos for pos in plots if hex_distance(pos[0], pos[1], cx, cy, width, wrap_x) <= r]
