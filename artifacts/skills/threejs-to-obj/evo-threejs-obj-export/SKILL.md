---
name: evo-threejs-obj-export
description: "Convert Three.js scene definitions to OBJ format for Blender import. Handles regular Mesh, InstancedMesh, nested transforms with non-uniform/mirrored scales, and coordinate system conversion (Y-up to Z-up via -90 degree X rotation). Use when converting Three.js code to simulation-ready 3D assets."
---

# Three.js to OBJ Export Skill

## Overview
Converts Three.js scene graphs to Wavefront OBJ format suitable for Blender import.

## Key Capabilities
- Handles regular `Mesh` objects with full world transform baking
- Handles `InstancedMesh` by expanding each instance with its per-instance transform
- Applies coordinate system conversion (-90° X rotation) from Three.js Y-up to Blender Z-up
- Properly handles non-uniform and mirrored scales (flips winding order when determinant < 0)
- Preserves normals with correct normal matrix transformation
- Manages OBJ 1-based index offsets across multiple objects

## Usage

The main export script is `scripts/export_obj.mjs`. It must be run from a directory
that has `three` in its `node_modules/` (e.g., `/root/`).

```javascript
// Fresh agent example - copy and run from /root/
import * as THREE from 'three';
import { createScene } from '/root/data/object.js';
import fs from 'fs';
import path from 'path';

const root = createScene();
const coordConvert = new THREE.Matrix4().makeRotationX(-Math.PI / 2);
root.updateMatrixWorld(true);

let output = '';
let indexVertex = 0;
let indexNormals = 0;
let indexUvs = 0;

function emitMeshGeometry(name, geometry, worldMatrix) {
  const finalMatrix = new THREE.Matrix4().copy(coordConvert).multiply(worldMatrix);
  const normalMatrix = new THREE.Matrix3().getNormalMatrix(finalMatrix);
  const det = finalMatrix.determinant();
  const flipWinding = det < 0;
  const vertices = geometry.getAttribute('position');
  const normals = geometry.getAttribute('normal');
  const uvs = geometry.getAttribute('uv');
  const indices = geometry.getIndex();
  if (!vertices) return;
  output += 'o ' + name + '\n';
  let nbVertex = 0, nbNormals = 0, nbUvs = 0;
  const v = new THREE.Vector3();
  for (let i = 0; i < vertices.count; i++) {
    v.fromBufferAttribute(vertices, i);
    v.applyMatrix4(finalMatrix);
    output += 'v ' + v.x + ' ' + v.y + ' ' + v.z + '\n';
    nbVertex++;
  }
  if (uvs) {
    const uv = new THREE.Vector2();
    for (let i = 0; i < uvs.count; i++) {
      uv.fromBufferAttribute(uvs, i);
      output += 'vt ' + uv.x + ' ' + uv.y + '\n';
      nbUvs++;
    }
  }
  if (normals) {
    const n = new THREE.Vector3();
    for (let i = 0; i < normals.count; i++) {
      n.fromBufferAttribute(normals, i);
      n.applyMatrix3(normalMatrix).normalize();
      output += 'vn ' + n.x + ' ' + n.y + ' ' + n.z + '\n';
      nbNormals++;
    }
  }
  if (indices !== null) {
    for (let i = 0; i < indices.count; i += 3) {
      let a = indices.getX(i), b = indices.getX(i+1), c = indices.getX(i+2);
      if (flipWinding) [b, c] = [c, b];
      const face = [];
      for (const j of [a, b, c]) {
        const vi = indexVertex + j + 1;
        let s = '' + vi;
        if (normals || uvs) {
          s += '/';
          if (uvs) s += (indexUvs + j + 1);
          if (normals) s += '/' + (indexNormals + j + 1);
        }
        face.push(s);
      }
      output += 'f ' + face.join(' ') + '\n';
    }
  } else {
    for (let i = 0; i < vertices.count; i += 3) {
      let a = i, b = i+1, c = i+2;
      if (flipWinding) [b, c] = [c, b];
      const face = [];
      for (const j of [a, b, c]) {
        const vi = indexVertex + j + 1;
        let s = '' + vi;
        if (normals || uvs) {
          s += '/';
          if (uvs) s += (indexUvs + j + 1);
          if (normals) s += '/' + (indexNormals + j + 1);
        }
        face.push(s);
      }
      output += 'f ' + face.join(' ') + '\n';
    }
  }
  indexVertex += nbVertex;
  indexUvs += nbUvs;
  indexNormals += nbNormals;
}

function traverseAndExport(object) {
  if (object.isMesh && !object.isInstancedMesh) {
    emitMeshGeometry(object.name || 'unnamed_mesh', object.geometry, object.matrixWorld);
  }
  if (object.isInstancedMesh) {
    const instanceMatrix = new THREE.Matrix4();
    for (let i = 0; i < object.count; i++) {
      object.getMatrixAt(i, instanceMatrix);
      const instanceWorld = new THREE.Matrix4().copy(object.matrixWorld).multiply(instanceMatrix);
      emitMeshGeometry((object.name || 'instanced') + '_' + i, object.geometry, instanceWorld);
    }
  }
  for (const child of object.children) traverseAndExport(child);
}

traverseAndExport(root);
fs.mkdirSync('/root/output', { recursive: true });
fs.writeFileSync('/root/output/object.obj', output);
console.log('Export complete');
```

## Architecture

### Key Functions
- `emitMeshGeometry(name, geometry, worldMatrix)` - Exports a single geometry with baked world transform
- `traverseAndExport(object)` - Recursively traverses scene graph, handling Mesh and InstancedMesh

### Coordinate Conversion
- Three.js: Y-up, right-handed
- Blender: Z-up, right-handed  
- Conversion: Apply -90° X rotation matrix before export
- Formula: `(x, y, z) -> (x, z, -y)`

### InstancedMesh Handling
The built-in Three.js OBJExporter does NOT support InstancedMesh. This skill:
1. Detects InstancedMesh via `object.isInstancedMesh`
2. Extracts per-instance matrices via `getMatrixAt()`
3. Composes: `finalMatrix = coordConvert * parentWorldMatrix * instanceMatrix`
4. Emits each instance as a separate named object

### Mirrored/Non-uniform Scale Handling
When a transform has negative determinant (mirrored scale), face winding order
is flipped to maintain correct surface normals in the output.
