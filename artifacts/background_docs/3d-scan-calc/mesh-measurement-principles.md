# Mesh measurement principles

Binary STL stores a header, a little-endian triangle count, and fixed-size
triangle records containing a normal, three vertices, and an attribute field.
Some producing applications repurpose the attribute field, so interpret it
only according to the supplied data documentation rather than assuming that it
is unused.

When a scan contains disconnected regions, construct connectivity from the
runtime vertices using a tolerance justified by the coordinate scale. Measure
components geometrically instead of assuming that file order, an identifier,
or triangle count determines the part of interest.

For a closed oriented triangle surface, enclosed volume can be obtained from a
signed tetrahedral sum. Check watertightness and winding behavior, then apply
the requested material data and units. Reopen the delivered artifact and
independently recompute a small sample before reporting the result.
