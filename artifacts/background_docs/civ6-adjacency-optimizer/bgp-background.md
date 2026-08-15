# Civilization VI — District Adjacency Bonus Reference (Gathering Storm)

A comprehensive reference for Civ6 district placement and adjacency bonus mechanics,
covering the Gathering Storm ruleset.

> Source: [Civilization Fandom Wiki — Adjacency bonus](https://civilization.fandom.com/wiki/Adjacency_bonus_(Civ6))
> and [District (Civ6)](https://civilization.fandom.com/wiki/District_(Civ6))

---

## 1. District Categories

### Specialty Districts
These count toward the **population-based district limit**:

CAMPUS, HOLY_SITE, THEATER_SQUARE, COMMERCIAL_HUB, HARBOR, INDUSTRIAL_ZONE,
ENTERTAINMENT_COMPLEX, WATER_PARK, ENCAMPMENT, AERODROME, GOVERNMENT_PLAZA,
DIPLOMATIC_QUARTER, PRESERVE

### Non-Specialty Districts
These do **NOT** count toward the population limit and can be built freely
(as long as placement prerequisites are met):

AQUEDUCT, DAM, CANAL, SPACEPORT, NEIGHBORHOOD

### Population Limit Formula

max specialty districts = 1 + floor((population − 1) / 3)

| Population | Max Specialty |
|------------|--------------|
| 1          | 1            |
| 4          | 2            |
| 7          | 3            |
| 9          | 3            |
| 10         | 4            |

Non-specialty districts like Aqueduct, Dam, and Neighborhood can be placed without
consuming specialty slots. They produce **no adjacency bonus of their own**, but
they **count as adjacent districts** for neighboring districts and some provide
special bonuses (e.g., Aqueduct/Dam/Canal each give Industrial Zone +2).

Because non-specialty districts are free from the population cap, they are among the
most powerful tools for boosting total adjacency yields. An Aqueduct placed between
an Industrial Zone and a Campus, for instance, gives the Industrial Zone +2 (special
bonus) while also contributing to the Campus's generic district count. Similarly,
Neighborhoods are unconstrained filler districts that can be placed to push neighboring
districts past the "2 adjacent districts" threshold needed for minor bonuses to start
yielding. Optimal city layouts almost always include multiple non-specialty districts
positioned to amplify the adjacency of nearby specialty districts.

---

## 2. Adjacency Bonus Rules by District

### 2.1 Minor Bonus Flooring Rule

Many districts receive "+1 per 2" of a source type. This is a **minor bonus** that
is counted **separately per source type**, then **each independently floored**.

For example, an Industrial Zone surrounded by 1 Mine, 1 Lumber Mill, and 1 generic
District gets floor(1/2) = 0 from each category, totaling 0 — not 1. Only when you
have 2+ of the same source type does the minor bonus yield anything.

This applies universally: Campus gets +1 per 2 Rainforests and +1 per 2 Districts,
Holy Site gets +1 per 2 Forests and +1 per 2 Districts, and so on. Having 1 adjacent
district always gives 0 from the district minor bonus; you need at least 2 adjacent
districts of the same counting category to get +1.

### 2.2 Independent Bonus Stacking

A neighboring district that provides a **specific major or standard bonus** also remains
a district for the generic minor adjacency rule. These are independent modifiers, not
mutually exclusive classifications. Count the specific rule and the generic district
rule separately, then floor the generic `+1 per 2 districts` contribution once its own
source count is complete.

For example, an Aqueduct next to an Industrial Zone supplies its specific major bonus
and also contributes one member of the Industrial Zone's generic district count. One
such neighbor does not create a whole generic point by itself; two adjacent districts
do. The same stacking principle applies to a Harbor beside a Commercial Hub, a City
Center beside a Harbor, and an Entertainment Complex or Water Park beside a Theater
Square.

### 2.3 Campus

| Adjacent Source           | Bonus             |
|---------------------------|--------------------|
| Geothermal Fissure        | +2 each            |
| Reef                      | +2 each            |
| Great Barrier Reef         | +2 each            |
| Mountain                  | +1 each            |
| Rainforest (Jungle)       | +1 per 2 (floored) |
| District (generic)        | +1 per 2 (floored) |

### 2.4 Holy Site

| Adjacent Source     | Bonus             |
|---------------------|--------------------|
| Natural Wonder      | +2 each            |
| Mountain            | +1 each            |
| Woods (Forest)      | +1 per 2 (floored) |
| District (generic)  | +1 per 2 (floored) |

### 2.5 Commercial Hub

| Source                  | Bonus             |
|-------------------------|--------------------|
| On River (self tile)    | +2                 |
| Adjacent Harbor         | +2 each            |
| District (generic)      | +1 per 2 (floored) |

The river bonus is a **self-tile** check: the Commercial Hub must be placed on a tile
that itself has a river edge. Being adjacent to a river tile is not enough — the river
must touch the Commercial Hub's own hex. In the game data, this means the tile's own
PlotRivers record must have at least one river flag set (IsNEOfRiver, IsWOfRiver, or
IsNWOfRiver), or a neighboring tile's river flag must indicate a shared river edge
with this tile. See Section 6 for details on how rivers are stored.

Note: City Center does **not** provide a special bonus to Commercial Hub. A Commercial
Hub adjacent to a City Center treats the City Center purely as a generic district for
the +1 per 2 minor bonus — it does not receive any +2 major bonus from it. Only
Harbor gives the Commercial Hub a +2 major adjacency bonus. This is a common point of
confusion because Harbor does get +2 from adjacent City Center, but that bonus is
one-directional and does not extend to Commercial Hub.

### 2.6 Industrial Zone

| Adjacent Source                  | Bonus             |
|----------------------------------|--------------------|
| Aqueduct / Bath / Dam / Canal    | +2 each            |
| Quarry (improvement)             | +1 each            |
| Strategic Resource               | +1 each            |
| Mine (improvement)               | +1 per 2 (floored) |
| Lumber Mill (improvement)        | +1 per 2 (floored) |
| District (generic)               | +1 per 2 (floored) |

### 2.7 Harbor

| Adjacent Source     | Bonus             |
|---------------------|--------------------|
| City Center         | +2 each            |
| Coastal Resource    | +1 each            |
| District (generic)  | +1 per 2 (floored) |

### 2.8 Theater Square

| Adjacent Source                       | Bonus             |
|---------------------------------------|--------------------|
| Wonder (built)                        | +2 each            |
| Entertainment Complex / Water Park    | +2 each            |
| District (generic)                    | +1 per 2 (floored) |

### 2.9 Districts That Receive No Adjacency Bonus

Aqueduct, Dam, Canal, Neighborhood, Spaceport — these districts do not receive
adjacency bonuses themselves, but still count as districts for their neighbors.
Their adjacency bonus is **0**, but they must still be included when reporting
per-district adjacency results. Every placed district — whether it scores or
not — must have a corresponding entry in any adjacency output (e.g.,
`"AQUEDUCT": 0`, `"DAM": 0`). Omitting zero-bonus districts from the output
is a common mistake that causes key-mismatch errors.

---

## 3. Feature Destruction

When any district **except City Center** is placed on a tile, the following are destroyed:

- Woods (FEATURE_FOREST)
- Rainforest (FEATURE_JUNGLE)
- Marsh (FEATURE_MARSH)
- Bonus Resources

Destruction affects adjacency calculations for neighboring districts. For example,
if you place a district on a Forest tile, that Forest no longer provides a Holy Site
bonus from adjacent tiles.

**Exception**: Settling a City Center preserves all features and resources on the tile
(e.g., a city on a Geothermal Fissure keeps it for Campus adjacency).

Adjacency should be computed **after** applying all destruction from placements.

---

## 4. District Placement Rules

### Universal Constraints
- Must be on **land** — Coast and Ocean tiles are forbidden for all districts except
  Harbor and Water Park (which *require* water)
- Must be within **3 hex tiles** of a City Center
- Cannot be placed on: Mountains, Natural Wonders, Strategic Resources, Luxury Resources,
  Geothermal Fissures
- Cannot overlap with existing districts
- CAN be placed on: Bonus resources (destroyed), Woods/Rainforest/Marsh (destroyed)

### District-Specific Placement

| District              | Special Requirements |
|-----------------------|---------------------|
| Harbor / Water Park   | Must be on Coast or Lake tile, adjacent to at least one land tile |
| Aerodrome / Spaceport | Must be on flat land (no hills, no water, no mountains) |
| Encampment / Preserve | Cannot be adjacent (distance 1) to City Center |
| Aqueduct              | Must be adjacent to City Center AND to a fresh water source (Mountain, Lake, Oasis, or River) |
| Dam                   | Must be on Floodplains tile with river traversing at least 2 hex edges |
| Canal                 | Must connect a water body to City Center, or connect two separate water bodies |

### City Center Placement
- Cannot be on water, mountains, natural wonders, or ice
- CAN be on resources and features (they are preserved)

---

## 5. Hex Grid Coordinate System

Civ6 uses **odd-row (odd-r) horizontal offset coordinates**.
Odd-numbered rows are shifted right by half a hex.

### Neighbor Offsets

Each hex has 6 neighbors. Because odd rows are shifted right, the relative positions
of diagonal neighbors differ between even and odd rows:

**Even rows** (y % 2 == 0):

| Direction | (dx, dy) |
|-----------|----------|
| East      | (+1, 0)  |
| NE        | (0, -1)  |
| NW        | (-1, -1) |
| West      | (-1, 0)  |
| SW        | (-1, +1) |
| SE        | (0, +1)  |

**Odd rows** (y % 2 == 1):

| Direction | (dx, dy) |
|-----------|----------|
| East      | (+1, 0)  |
| NE        | (+1, -1) |
| NW        | (0, -1)  |
| West      | (-1, 0)  |
| SW        | (0, +1)  |
| SE        | (+1, +1) |

### Offset-to-Cube Conversion

To convert odd-r offset coordinates (x, y) to cube coordinates (q, r, s):

```
q = x - (y - (y % 2)) / 2
r = y
s = -q - r
```

(Note: `(y - (y % 2)) / 2` is integer division; equivalently `(y - (y & 1)) // 2`.)

### Hex Distance

Hex distance between two tiles a and b: convert both to cube coordinates, then:

```
distance = max(|qa - qb|, |ra - rb|, |sa - sb|)
```

This is equivalent to half the cube Manhattan distance: `(|dq| + |dr| + |ds|) / 2`.

---

## 6. .Civ6Map File Format

The `.Civ6Map` file is a **SQLite database**. Key tables:

| Table          | Key Columns                                          |
|----------------|------------------------------------------------------|
| Map            | Width, Height, WrapX, WrapY, MapSizeType             |
| Plots          | ID (= y × Width + x), TerrainType, IsImpassable      |
| PlotFeatures   | ID, FeatureType                                       |
| PlotResources  | ID, ResourceType, ResourceCount                       |
| PlotRivers     | ID, IsNEOfRiver, IsWOfRiver, IsNWOfRiver (boolean flags) |
| PlotAttributes | ID, Type, Name, Value                                 |

**Important**: The `.Civ6Map` file stores only the **natural map state** — terrain,
features, resources, and rivers. It does **not** contain tile improvements (Mines,
Quarries, Lumber Mills, Farms, etc.) because improvements are built during gameplay
and are not part of the map editor format. This means adjacency bonuses that depend on
improvements (e.g., Industrial Zone +1 per Quarry, +1 per 2 Mines) **cannot be computed
from the map file** and should be treated as 0 in placement optimization. Similarly,
built Wonders are not stored in the map file, so Theater Square's +2 per Wonder
adjacency is not applicable.

### Terrain Types

Base: `TERRAIN_GRASS`, `TERRAIN_PLAINS`, `TERRAIN_DESERT`, `TERRAIN_TUNDRA`,
`TERRAIN_SNOW`, `TERRAIN_COAST`, `TERRAIN_OCEAN`

Variants: append `_HILLS` or `_MOUNTAIN` (e.g., `TERRAIN_GRASS_HILLS`,
`TERRAIN_PLAINS_MOUNTAIN`)

### Feature Types

`FEATURE_FOREST` (Woods), `FEATURE_JUNGLE` (Rainforest), `FEATURE_MARSH`,
`FEATURE_REEF`, `FEATURE_ICE`, `FEATURE_GEOTHERMAL_FISSURE`,
`FEATURE_FLOODPLAINS`, `FEATURE_OASIS`, etc.

### Plot ID ↔ Coordinates

Plot IDs are stored in row-major order: plot_id = y × map_width + x.
To recover coordinates: x = plot_id mod map_width, y = plot_id div map_width.

### River Storage and Detection

Rivers in Civ6 run along hex **edges**, not through hex centers. The PlotRivers table
stores three boolean flags per plot, each indicating whether a river runs along a
specific edge of that hex: the northeast edge (IsNEOfRiver), the west edge
(IsWOfRiver), and the northwest edge (IsNWOfRiver). Each flag being true means there
is a river segment on that particular edge of the tile.

A tile "has a river" (relevant for Commercial Hub +2 bonus) if **any** river edge
touches it. Since each river edge is shared between two hexes, a tile can have a river
even if its own PlotRivers flags are all false — the river might be recorded on an
adjacent tile's flags instead. Specifically, a tile is on a river if any of the
following are true: (1) any of its own three river flags is set, or (2) any of its
neighbors has a river flag set for the edge shared with this tile. For example, if the
tile to the east has IsWOfRiver = true, that river runs along the shared edge between
the two tiles, so both tiles are considered to be on a river.

To correctly determine whether a hex is river-adjacent for Commercial Hub placement,
you must check both the tile's own flags and the complementary flags of all six
neighbors.

---

## 7. Optimization Principles

1. **Maximize non-specialty district usage**: Aqueduct, Dam, Canal, and Neighborhood are
   free to place and serve as adjacency boosters for neighboring specialty districts.
   In practice, the difference between a good layout and a great layout often comes down
   to how many non-specialty districts are deployed as adjacency multipliers. Always
   consider whether placing an Aqueduct, Dam, or Neighborhood could push a nearby
   specialty district's minor bonus past a flooring threshold.

2. **Industrial Zone synergy**: Place Industrial Zone adjacent to Aqueduct and Dam for
   +2 each. Both infrastructure districts also remain members of the generic district
   count, whose minor contribution is calculated independently and floored after counting.

3. **Cluster districts**: Since minor bonuses require 2+ adjacent districts, clustering
   districts together yields more than spreading them out. A lone specialty district
   surrounded by terrain may get 0 from the district minor bonus, while the same district
   in a cluster of 3+ districts picks up meaningful minor bonus points.

4. **Leverage terrain features**: Mountains (+1 each for Campus and Holy Site), Reefs
   (+2 each for Campus), and Rivers (+2 for Commercial Hub on-tile) are high-value.
   For Commercial Hub river placement, verify the tile actually has a river edge — being
   near a river is not the same as being on one.

5. **Watch for destruction**: Don't place a district on a tile whose feature benefits a
   neighbor. For example, placing a district on a Forest tile destroys the Forest bonus
   that an adjacent Holy Site would have received.

6. **Verify adjacency calculations independently**: When computing total adjacency for a
   layout, always recalculate each district's bonus from scratch using the rules above
   rather than estimating. The per-source flooring rule, independent modifier stacking, and feature
   destruction can each silently reduce expected bonuses. A reported total should always
   equal the sum of individually calculated per-district bonuses.

### 7.1 Algorithm Complexity Warning

Civ6 maps can contain 1000+ tiles. Exhaustive enumeration of all possible district
placements is computationally infeasible — even a single city with 5 districts has
billions of placement combinations on a large map. Use a **greedy or heuristic
approach**: score candidate tiles for each district type independently, then place
districts one at a time in decreasing priority order, re-scoring neighbors after
each placement. A greedy algorithm that evaluates ~100 candidate tiles per district
runs in seconds; brute-force combinatorial search will time out.

### 7.2 Feature-Driven Placement

Adjacency bonuses are almost entirely determined by **terrain features**, not by
abstract tile positions. Experienced Civ6 players never scan the map tile by tile —
they locate the high-value feature clusters first and build around them:

- **Mountains** are the strongest universal feature: +1 each for Campus and Holy Site.
  A cluster of 2–3 mountains in a line creates a natural "spine" to place Campus and
  Holy Site along.
- **Geothermal Fissures** (+2 for Campus) and **Reefs** (+2 for Campus) are rare but
  extremely high-value. A Campus adjacent to even one of these plus a mountain is
  already at +3 before district bonuses.
- **Floodplains** indicate where Dams can be placed, and Dams give Industrial Zone +2.
  Look for floodplains near mountains — this enables the IZ+Dam+Aqueduct cluster that
  yields +4 or more for a single Industrial Zone.
- **Rivers** give Commercial Hub +2 (self-tile check). River tiles near other district
  clusters are prime Commercial Hub sites.

A city location with no mountains, geothermal fissures, reefs, or rivers within 3 tiles
has an **adjacency ceiling near zero** — it can only get minor bonuses from district
clustering, which rarely exceeds 2–3 total. Such locations are never worth considering
in an optimization context.

### 7.3 District Synergy Clusters

High-scoring layouts follow a small number of recognizable **cluster patterns** rather
than scattered placements:

1. **Industrial cluster**: Industrial Zone adjacent to Aqueduct (+2) and Dam (+2), with
   the Aqueduct also adjacent to City Center (placement requirement) and a fresh water
   source. This alone gives IZ +4, and any other adjacent districts add minor bonuses.

2. **Science cluster**: Campus next to 1–2 mountains and/or a geothermal fissure/reef.
   Place Neighborhood or other districts adjacent to the Campus to push its district
   minor bonus past the floor(2/2) = 1 threshold.

3. **Faith cluster**: Holy Site along a mountain range with preserved forests on
   neighboring tiles (remember: placing a district on a forest tile destroys it, so
   leave forests unbuilt to benefit the Holy Site).

4. **Commerce cluster**: Commercial Hub on a river tile, adjacent to a Harbor if the
   city has coast access.

The best total adjacency comes from **overlapping** these clusters so that a single
non-specialty district (Aqueduct, Neighborhood) serves as an adjacency booster for
multiple specialty districts simultaneously.

### 7.4 Practical Adjacency Ceilings

Understanding the realistic per-district ceiling helps prioritize which districts to
include:

| District        | Typical ceiling (map-only, no improvements) | Key drivers                  |
|-----------------|----------------------------------------------|------------------------------|
| Campus          | 5–8                                          | Geothermal (+2), Reef (+2), Mountains (+1 each), districts |
| Industrial Zone | 4–6                                          | Aqueduct (+2), Dam (+2), districts |
| Holy Site       | 3–5                                          | Mountains (+1 each), preserved Forests, districts |
| Commercial Hub  | 2–4                                          | River (+2), Harbor (+2), districts |
| Harbor          | 2–4                                          | City Center (+2), coastal resources |
| Theater Square  | 0–2                                          | Only district minor bonuses (no Wonders in map file) |

Campus and Industrial Zone have the highest adjacency potential from map features alone.
Theater Square is almost never worth including when optimizing purely from a .Civ6Map
file, because its main sources (built Wonders and Entertainment Complexes) are not
present in the map editor format.
