# Scene-graph export principles

A scene graph combines each object's local transform with its ancestors. Before
export, update the hierarchy, traverse every geometry-bearing node, and bake
the complete world transform. Instanced geometry also has a per-instance
transform that must be composed separately for each copy.

Coordinate-system conversion is a source-to-target convention, not a guessed
constant. Derive the mapping from the public conventions of the two formats and
apply it consistently to positions, normals, winding, and mirrored transforms.

OBJ indices are one-based and may refer independently to positions, texture
coordinates, and normals. Preserve all geometry while managing index offsets
across objects. Validate the delivered file by loading it with an independent
reader and checking object counts, bounds, orientation, and representative
transformed vertices against the runtime scene.
