# Geospatial Analysis of Earthquakes and Tectonic Plate Boundaries

This document provides background on tectonic plate geometry, spatial containment testing, geodesic distance computation, and the data formats used in plate boundary models and seismic catalogs. It is intended to equip an analyst with the reasoning needed to perform geospatial queries that relate earthquake locations to plate geometries.

## Tectonic Plates and the PB2002 Model

The Peter Bird 2002 (PB2002) model is the standard digital representation of Earth's tectonic plates. It encodes two complementary datasets:

- **Plate polygons** (`PB2002_plates`): Each tectonic plate is represented as a polygon (or multipolygon) in geographic coordinates (EPSG:4326, longitude/latitude). Every feature carries a `PlateName` (e.g., "Pacific", "North America") and a two-letter `Code` (e.g., "PA", "NA"). These polygons tile the entire globe without gaps or overlaps.

- **Plate boundaries** (`PB2002_boundaries`): The edges between adjacent plates are stored as LineString features. Each boundary segment has a `Name` field composed of the two-letter codes of the plates it separates (e.g., "PA-NA", "PA/AU"). The separator character encodes boundary type:
  - `-` (hyphen): divergent or transform boundary
  - `/` (forward slash): convergent boundary (subduction), with the overriding plate listed first
  - `\` (backslash): convergent boundary (subduction), with the overriding plate listed second

A single plate may have dozens of boundary segments shared with many neighbors. The Pacific plate, for example, has boundary segments with the North American, Australian, Nazca, Antarctic, Philippine Sea, Juan de Fuca, Cocos, and many other plates. To collect all boundary geometry for a given plate, one must filter for all boundary segments whose `Name` field contains that plate's two-letter code.

### The Pacific Plate and the Antimeridian

The Pacific plate is the largest tectonic plate on Earth, spanning much of the Pacific Ocean basin. Its geometry presents a significant computational challenge: the plate straddles the antimeridian (the 180th meridian), meaning its polygon coordinates wrap from -180 to +180 degrees longitude. In GeoJSON and many geospatial libraries, the antimeridian is handled by splitting the plate into a **MultiPolygon** with multiple polygon parts rather than a single contiguous ring. Analysts must ensure their spatial operations correctly handle MultiPolygon geometries and do not inadvertently split or lose parts of the plate.

## Spatial Containment: Point-in-Polygon Testing

Determining whether an earthquake occurred within a particular tectonic plate requires a **point-in-polygon** test. Given an earthquake's longitude and latitude coordinates and a plate's polygon geometry, the test returns true if the point falls inside the polygon boundary.

Key considerations:

- **Coordinate reference system (CRS)**: Both the earthquake points and the plate polygons must share the same CRS. The PB2002 data and USGS earthquake catalogs both use EPSG:4326 (WGS 84 geographic coordinates). Point-in-polygon containment testing should be performed in this native CRS, not in a projected CRS, to avoid distortion artifacts at plate edges.

- **MultiPolygon handling**: When a plate is represented as a MultiPolygon (as with the Pacific plate), the containment test must check all constituent polygons. Standard geospatial libraries handle this automatically when using spatial containment methods on unified geometry objects.

- **Boundary points**: Points that fall exactly on a polygon boundary are typically considered "not within" by most computational geometry implementations. For earthquake analysis this rarely matters, since seismic coordinates have finite precision and exact boundary coincidence is vanishingly unlikely.

- **Geometry union**: When a plate has multiple geometry parts (rows in a spatial dataset), combining them into a single unified geometry object allows all containment tests to be run efficiently against one geometry rather than iterating over parts.

## Distance Computation on the Earth's Surface

Computing the distance from an earthquake epicenter to the nearest plate boundary requires careful handling of coordinate systems and projections.

### Why Projection Matters

Geographic coordinates (longitude, latitude in degrees) do not have uniform metric spacing. One degree of longitude represents approximately 111 km at the equator but shrinks to zero at the poles. Computing Euclidean distance directly on degree-valued coordinates produces meaningless numbers that conflate angular separation with physical distance. To obtain distances in kilometers, both the earthquake points and the boundary geometries must first be **projected** into a metric (Cartesian) coordinate reference system.

### Choosing a Projection

Several projections are suitable for computing distances across large geographic extents:

| Projection | EPSG Code | Properties | Best Use |
|---|---|---|---|
| WGS 84 / World Equidistant Cylindrical | EPSG:4087 | Equidistant along meridians; moderate area distortion | Global distance measurements |
| Web Mercator | EPSG:3857 | Conformal; extreme area distortion at high latitudes | Web mapping only; poor for distance |
| UTM zones | EPSG:326xx | Conformal, low distortion within 6-degree zones | Local/regional analysis |
| Lambert Azimuthal Equal-Area | varies | Equal-area; distortion increases away from center | Continental-scale area analysis |

For analyses spanning an entire ocean basin (such as the Pacific plate, which extends from the Southern Ocean to the Aleutian Islands), a global equidistant projection like **EPSG:4087** is appropriate. UTM zones are too narrow, and Web Mercator introduces unacceptable distortion at the high latitudes where parts of the Pacific plate extend.

### Computing Distance to a Boundary

The distance from a point to a plate boundary is the **minimum distance** from that point to any part of the boundary's line geometry. When the boundary consists of multiple line segments (as plate boundaries always do), this means finding the closest point on any segment. The workflow is:

1. **Collect all relevant boundary segments**: Filter the boundary dataset for all segments that involve the plate of interest (e.g., all segments whose `Name` contains "PA" for the Pacific plate).
2. **Combine into a single geometry**: Merge all filtered boundary LineStrings into a single MultiLineString. This allows a single distance call to find the minimum distance across all segments.
3. **Project both geometries**: Transform both the earthquake points and the merged boundary geometry into the chosen metric CRS.
4. **Compute distance**: Use the geometry library's distance method, which returns the minimum Euclidean distance in the CRS's native units (meters for EPSG:4087). Divide by 1000 to convert to kilometers.

### Filtering Boundaries by Plate Code

Boundary segments in the PB2002 model use two-letter plate codes in the `Name` field. To collect all boundaries of the Pacific plate, filter for segments where "PA" appears anywhere in the `Name` string. This captures all boundary types regardless of separator character or ordering (e.g., "PA-NA", "NA/PA", "PA\\OK" all match).

Be careful not to over-filter. A common mistake is to filter only for boundaries where the plate code appears in a specific position (e.g., only as `PlateA`), which would miss half the boundary segments.

## USGS Earthquake Catalog Format

The USGS earthquake catalog is distributed as GeoJSON FeatureCollections. Each earthquake is a Feature with:

- **Geometry**: A Point with coordinates as `[longitude, latitude, depth_km]`. Note the GeoJSON convention: longitude comes first, latitude second.
- **Properties**: Include `mag` (magnitude), `place` (human-readable location description), `time` (Unix timestamp in **milliseconds** since epoch), and `type` (event type, typically "earthquake").
- **Feature ID**: A unique event identifier string (e.g., the synthetic value `"demo-event-001"`). Actual identifiers must be read from the supplied catalog.

### Time Format Conversion

The USGS catalog stores earthquake times as Unix timestamps in **milliseconds** (not seconds). To convert to ISO 8601 format:

1. Divide the timestamp by 1000 to get seconds since epoch.
2. Convert to a UTC datetime object.
3. Format as `YYYY-MM-DDTHH:MM:SSZ`.

Failing to divide by 1000 will produce dates thousands of years in the future.

## Geospatial Workflow Patterns

Geospatial analysis libraries extend tabular data structures with geometry columns and spatial operations. The typical workflow for this class of geospatial analysis follows a consistent pattern:

1. **Load data**: Read GeoJSON files directly, or construct a spatial dataset from a list of geometry objects with an explicit CRS.
2. **Spatial filter**: Use boolean indexing with containment or intersection methods to subset features by spatial relationship.
3. **Project**: Transform geometries to a target CRS before computing distances or areas.
4. **Compute**: Use distance methods for minimum distance between geometries, area properties for polygon areas, etc.
5. **Aggregate**: Use standard tabular operations (sorting, filtering, ranking) on computed columns.

When constructing a spatial dataset from raw coordinate data, the CRS must be specified explicitly as EPSG:4326. Omitting the CRS will cause subsequent coordinate transformations to fail.

## Domain-Specific Nuances

- **Distance computations require a metric coordinate reference system.** Computing distances directly in EPSG:4326 (degrees) without projecting to a metric CRS produces incorrect results. One degree of latitude is roughly 111 km, but one degree of longitude varies from 111 km at the equator to 0 km at the poles. Any distance calculation on unprojected geographic coordinates silently returns values in degrees rather than physical distance units.

- **Plate boundary geometry must include all adjacent-plate segments.** The Pacific plate has boundaries with many other plates. Filtering boundaries by only one neighbor (e.g., only "PA-NA") instead of all segments containing "PA" captures only a fraction of the boundary and produces inflated distance values for earthquakes near other boundary segments.

- **GeoJSON coordinate ordering places longitude first.** GeoJSON uses `[longitude, latitude]` ordering, while many other formats and APIs use `[latitude, longitude]`. Transposing these coordinates produces geometrically valid but geographically incorrect points -- a point intended for the Pacific Ocean may end up in Central Asia, or vice versa.

- **The USGS catalog expresses timestamps in milliseconds since the Unix epoch.** This differs from the more common convention of seconds since epoch. The millisecond timestamp must be divided by 1000 before conversion to a datetime representation; otherwise, the resulting dates will be thousands of years in the future.

- **Global projections are required for plate-scale analysis.** Local projections such as individual UTM zones cover only 6 degrees of longitude. The Pacific plate spans nearly 180 degrees of longitude, so a single UTM zone would introduce severe distortion for most of the plate's extent. A global equidistant projection (such as EPSG:4087) is appropriate for distance measurements across such large regions.

- **The Pacific plate is stored as a MultiPolygon due to the antimeridian.** Because the plate crosses the 180th meridian, it is split into multiple polygon components. Spatial operations that assume a single contiguous Polygon -- for instance, accessing only the first coordinate ring -- may silently analyze only one fragment of the plate and miss earthquakes located in other fragments.

- **Computed floating-point distances carry false precision from projection arithmetic.** Distances derived from coordinate transformations and geometric computations should be rounded to an appropriate number of decimal places for reporting. Unrounded values suggest a level of precision that the underlying data and projection do not support.

- **Plate polygons and plate boundaries serve distinct analytical purposes.** The plate polygon dataset defines the spatial extent of each plate (for containment testing), while the boundary dataset defines the linear edges between plates (for distance computation). These are complementary datasets: polygon edges are simplified outlines, while the dedicated boundary LineStrings carry higher-resolution geometry with additional metadata about boundary type.
