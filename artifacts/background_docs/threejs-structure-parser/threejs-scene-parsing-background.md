# Parsing Three.js Scene Graphs and Exporting Mesh Geometry

This document provides background on how Three.js organizes 3D objects in a hierarchical scene graph, how to programmatically traverse that graph to identify parts and meshes, and how to correctly export geometry to the OBJ file format with proper world-space transformations applied.

## Three.js Scene Graph Fundamentals

Three.js represents 3D scenes as a tree of Object3D nodes. Every visible object, grouping container, camera, and light inherits from Object3D and participates in a parent-child hierarchy. The two most important node types for structural parsing are:

- **Group** -- A pure organizational container with no geometry of its own. Groups define logical "parts" or assemblies. A group can contain meshes, other groups, or any Object3D.
- **Mesh** -- A visible object that pairs a BufferGeometry (shape data) with a Material (appearance). Meshes are the leaf nodes that carry actual vertex data.

A typical scene graph for a multi-part mechanical object looks like this:

The root node (a Group) contains two child Groups: `assembly_A` and `assembly_B`. Under `assembly_A`, there are two Mesh children (`component_1`, `component_2`) and a nested `sub_assembly` Group that itself contains `component_3` (Mesh) and `component_4` (Mesh). Under `assembly_B`, there are two Mesh children: `component_5` and `component_6`.

Key properties on every node:

| Property | Type | Purpose |
|---|---|---|
| `name` | `string` | Human-readable identifier (may be empty) |
| `parent` | `Object3D` | Reference to the immediate parent node |
| `children` | `Object3D[]` | Array of direct child nodes |
| `position` | `Vector3` | Translation relative to the parent |
| `rotation` | `Euler` | Rotation relative to the parent |
| `quaternion` | `Quaternion` | Rotation in quaternion form (synced with `rotation`) |
| `scale` | `Vector3` | Scale relative to the parent |
| `matrix` | `Matrix4` | Local transform matrix (composed from position/rotation/scale) |
| `matrixWorld` | `Matrix4` | Accumulated world transform from root to this node |

## Traversal and Part Discovery

Three.js provides two primary mechanisms for walking the scene graph:

### The traverse() Method

The traverse method on the root node visits every descendant (depth-first) including the root itself. Inside the callback, you can check the node type to distinguish Groups (organizational containers) from Meshes (geometry-bearing nodes). These type checks let you dispatch different logic for organizational containers versus visible geometry.

### Determining Part Membership

A mesh belongs to the nearest named Group ancestor in the hierarchy. To find which part a mesh belongs to, walk up the parent chain until you reach a Group with a non-empty name property. That group is the owning "part." If no named group is found, continue to the root.

This distinction matters because a Group may be nested inside another Group. The immediate named Group parent is the direct owner. Depending on the desired decomposition, you may want only the closest named group, or you may need to account for the full nesting hierarchy.

### Groups With No Direct Meshes

Not every Group in the scene graph will have mesh children. The root node itself is often a Group that serves purely as a container for sub-assemblies. When collecting part-level structure, filter out groups that contain zero meshes (directly or through child groups), as they represent organizational scaffolding rather than geometric parts.

## World-Space Transforms and Matrix Updates

Each node stores its transform **relative to its parent**. The matrixWorld property accumulates all ancestor transforms to give the node's absolute position, rotation, and scale in the global coordinate frame. However, matrixWorld is not automatically kept up to date -- it is recomputed during the render loop or when explicitly requested.

Before reading geometry in world space, the world matrix must be updated recursively from the root node. A forced recursive update of the entire subtree ensures that all descendant nodes have current world transforms. Without this step, matrixWorld may contain stale or identity values, producing geometry that appears at the origin or in incorrect orientations.

### Applying the World Transform to Geometry

A mesh's geometry stores vertices in **local space** (relative to the mesh's own origin). To obtain vertices in world space, the mesh's world transform matrix must be applied to the geometry.

The standard approach is to clone the mesh's geometry (to avoid mutating the original shared geometry) and then apply the mesh's world transform matrix to the clone. This transforms every vertex from local coordinates into world coordinates.

This is critical for correct export. Without this step, meshes that have been positioned, rotated, or scaled via the scene graph hierarchy will export with incorrect vertex positions. For example, a cylinder created at the origin and then repositioned to a different location will export centered at the origin unless the world transform is applied.

## Geometry Construction Patterns in Three.js

Three.js provides parametric geometry classes that generate BufferGeometry instances. Understanding how these work is essential for predicting vertex layouts and orientations.

### Common Geometry Types

| Geometry Class | Default Orientation | Key Parameters |
|---|---|---|
| BoxGeometry | Centered at origin, aligned to axes | width (X), height (Y), depth (Z) |
| CylinderGeometry | Centered at origin, aligned along **Y axis** | radiusTop, radiusBottom, height, radialSegments |
| SphereGeometry | Centered at origin | radius, widthSegments, heightSegments |
| TorusGeometry | Centered at origin, lying in the **XY plane** | radius, tube, radialSegments, tubularSegments |
| ConeGeometry | Centered at origin, aligned along **Y axis** | radius, height, radialSegments |

### The Cylinder-Between-Two-Points Pattern

A very common pattern in structural 3D models is creating a cylinder that connects two arbitrary points (a "beam" or "strut"). Since CylinderGeometry is always created along the Y axis, connecting two points requires:

1. Compute the direction vector and length between the two points.
2. Create a CylinderGeometry with the computed length.
3. Compute a quaternion rotation from the Y axis to the direction vector.
4. Position the mesh at the midpoint between the two points.

First, compute the direction vector by subtracting point1 from point2, then get its length. Create a CylinderGeometry with that length. Compute a quaternion rotation from the unit Y axis (0, 1, 0) to the normalized direction vector. Finally, position the mesh at the midpoint between the two points by copying point1 and adding half the direction vector.

When exporting this mesh, the local geometry (a Y-aligned cylinder) must be transformed by the mesh's world transform to place it correctly between the two intended endpoints.

### Indexed vs. Non-Indexed Geometry

Three.js geometries can be **indexed** (vertices shared between faces via an index buffer) or **non-indexed** (every triangle has its own unique vertices). Many parametric geometries are indexed by default.

For export purposes, indexed geometry should be converted to non-indexed form to ensure every face has explicit vertices. If the geometry has an index, it should be converted to non-indexed form where every triangle has its own explicit vertex data.

Additionally, if the geometry lacks normal vectors (needed for proper shading in OBJ files), they must be computed. Generating vertex normals ensures proper shading information is available for the exported file.

## The OBJ File Format

OBJ (Wavefront) is a simple text-based 3D geometry format. It stores vertices, texture coordinates, normals, and face definitions line by line.

### OBJ Syntax

An OBJ file is composed of the following line types:

- Lines beginning with `#` are comments.
- Lines beginning with `o` followed by a name declare an object (e.g., `o ObjectName`).
- Lines beginning with `v` followed by three floats declare a vertex position (x, y, z).
- Lines beginning with `vn` followed by three floats declare a vertex normal (nx, ny, nz).
- Lines beginning with `vt` followed by two floats declare a texture coordinate (u, v) -- this is optional.
- Lines beginning with `f` declare a face by referencing vertex and normal indices in the format `v1//n1 v2//n2 v3//n3` (where indices are 1-based).

Key rules:

- **Vertex lines** begin with `v` followed by three floating-point coordinates (x, y, z).
- **Normal lines** begin with `vn` followed by the normal vector components.
- **Face lines** begin with `f` followed by vertex references. Each reference can be `v`, `v/vt`, `v//vn`, or `v/vt/vn` where indices are 1-based.
- Multiple objects can appear in one file, separated by `o ObjectName` lines.
- The format is purely geometric -- no materials, animations, or hierarchy.

### Exporting with OBJExporter

Three.js provides an OBJExporter in its examples/addons package. The exporter serializes a mesh's geometry into OBJ format. It uses the mesh's name property as the object name in the output. The exporter operates on the geometry as-is, so world transforms must be baked into the geometry beforehand for correct output.

## Merging Geometries for Composite Parts

When a logical part (a Group) contains multiple meshes, it is often useful to produce a single merged OBJ that represents the entire part. Three.js provides a geometry merge utility in BufferGeometryUtils.

For each mesh, clone its geometry, apply the world transform to place it in world space, convert to non-indexed form if it has an index, and compute vertex normals if they are missing. Collect all prepared geometries into an array, then merge them into a single BufferGeometry. Wrap the result in a new Mesh.

When merging, the geometries should not be grouped into separate draw groups -- they are combined into a single unified geometry. All geometries must have compatible attribute sets (same attributes with the same item sizes) for merging to succeed.

This merge-then-export pattern produces a single OBJ file whose vertices are the union of all constituent meshes, each in world space.

## Key Distinctions in Practice

- **World matrix updates must precede traversal.** The world transform on child nodes is recomputed only when explicitly requested or during rendering. Before any traversal that reads geometry in world space, the world matrix must be updated recursively from the root. Otherwise, child node transforms may be identity matrices, causing all geometry to collapse to the origin.

- **Exported geometry must be in world space.** If geometry is exported without first applying the mesh's world transform to a cloned copy, the exported vertices will be in local space. For meshes that have been positioned or rotated via the scene graph, this produces incorrect output.

- **Group nesting levels determine part ownership.** A mesh's immediate parent may itself be a child of another group. Walking up the parent chain and stopping at the first named Group gives the direct owning part, but the scene may have deeper nesting. The traversal strategy must match the desired part decomposition.

- **Only groups containing meshes represent geometric parts.** The root node and intermediate organizational groups may have names but no mesh geometry. These represent structural scaffolding rather than exportable parts, and including them in output produces empty geometry files.

- **Indexed geometry requires conversion for consistent export.** Many parametric geometries (Box, Cylinder, Torus, etc.) are indexed by default. Converting to non-indexed form before export ensures consistent output across different geometry types.

- **Geometry cloning preserves shared references.** Applying a world transform directly to a geometry that is shared across multiple meshes will affect all of them. Standard practice is to clone the geometry before applying any transforms. This is one of the most common bugs in Three.js export pipelines: if you call `geometry.applyMatrix4(mesh.matrixWorld)` without cloning first, every mesh that references that same geometry object will be silently corrupted. The correct pattern is `const exportGeometry = mesh.geometry.clone().applyMatrix4(mesh.matrixWorld)`. This applies to all export scenarios — OBJ, STL, GLTF — whenever world-space coordinates are needed.

- **The name property serves as the primary identifier.** Mesh and group names are the primary mechanism for identifying parts in the output. Some meshes may have empty names, which requires generating fallback identifiers.

- **Default orientations are part of the transform chain.** CylinderGeometry aligns along Y, TorusGeometry lies in XY. If rotations are applied to reorient these shapes (e.g., rotating a torus by 90 degrees to make it vertical), these rotations are part of the transform chain and are captured in the world transform matrix.

## Running Three.js in Node.js (Server-Side)

Three.js is primarily a browser library, but its core classes (Group, Mesh, BufferGeometry, Vector3, Matrix4, etc.) work in Node.js without a DOM or WebGL context. Geometry creation, scene graph manipulation, and OBJ export are all CPU-based operations that do not require a GPU or canvas.

To use Three.js in Node.js, import the main Three.js module, the OBJExporter from the examples/addons exporters directory, and the merge utility from the examples/addons BufferGeometryUtils module.

The scene file can be dynamically imported if it uses ES module exports. Converting a filesystem path into a proper file:// URL (using Node's url module) is necessary because Node.js dynamic imports require a proper URL, not a bare filesystem path. The imported module's exported scene creation function can then be called to obtain the root node.
