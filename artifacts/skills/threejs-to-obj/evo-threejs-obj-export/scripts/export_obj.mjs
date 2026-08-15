import * as THREE from 'three';
import { createScene } from '/root/data/object.js';
import fs from 'fs';
import path from 'path';

// Build the scene
const root = createScene();

// Apply -90 degree X rotation for Y-up (Three.js) -> Z-up (Blender)
const coordConvert = new THREE.Matrix4().makeRotationX(-Math.PI / 2);

// Update all world matrices
root.updateMatrixWorld(true);

// OBJ export state
let output = '';
let indexVertex = 0;
let indexNormals = 0;
let indexUvs = 0;

function emitMeshGeometry(name, geometry, worldMatrix) {
  // Compose the coordinate conversion with the world matrix
  const finalMatrix = new THREE.Matrix4().copy(coordConvert).multiply(worldMatrix);
  
  const normalMatrix = new THREE.Matrix3().getNormalMatrix(finalMatrix);
  
  // Check if the transform has a negative determinant (mirrored/flipped)
  const det = finalMatrix.determinant();
  const flipWinding = det < 0;
  
  const vertices = geometry.getAttribute('position');
  const normals = geometry.getAttribute('normal');
  const uvs = geometry.getAttribute('uv');
  const indices = geometry.getIndex();
  
  if (!vertices) return;
  
  output += 'o ' + name + '\n';
  
  let nbVertex = 0;
  let nbNormals = 0;
  let nbUvs = 0;
  
  // Vertices
  const v = new THREE.Vector3();
  for (let i = 0; i < vertices.count; i++) {
    v.fromBufferAttribute(vertices, i);
    v.applyMatrix4(finalMatrix);
    output += 'v ' + v.x + ' ' + v.y + ' ' + v.z + '\n';
    nbVertex++;
  }
  
  // UVs
  if (uvs) {
    const uv = new THREE.Vector2();
    for (let i = 0; i < uvs.count; i++) {
      uv.fromBufferAttribute(uvs, i);
      output += 'vt ' + uv.x + ' ' + uv.y + '\n';
      nbUvs++;
    }
  }
  
  // Normals
  if (normals) {
    const n = new THREE.Vector3();
    for (let i = 0; i < normals.count; i++) {
      n.fromBufferAttribute(normals, i);
      n.applyMatrix3(normalMatrix).normalize();
      output += 'vn ' + n.x + ' ' + n.y + ' ' + n.z + '\n';
      nbNormals++;
    }
  }
  
  // Faces
  if (indices !== null) {
    for (let i = 0; i < indices.count; i += 3) {
      let a = indices.getX(i);
      let b = indices.getX(i + 1);
      let c = indices.getX(i + 2);
      
      // Flip winding order if determinant is negative
      if (flipWinding) {
        [b, c] = [c, b];
      }
      
      const face = [];
      for (const j of [a, b, c]) {
        const vi = indexVertex + j + 1;
        let faceStr = '' + vi;
        if (normals || uvs) {
          faceStr += '/';
          if (uvs) faceStr += (indexUvs + j + 1);
          if (normals) faceStr += '/' + (indexNormals + j + 1);
        }
        face.push(faceStr);
      }
      output += 'f ' + face.join(' ') + '\n';
    }
  } else {
    for (let i = 0; i < vertices.count; i += 3) {
      let a = i;
      let b = i + 1;
      let c = i + 2;
      
      if (flipWinding) {
        [b, c] = [c, b];
      }
      
      const face = [];
      for (const j of [a, b, c]) {
        const vi = indexVertex + j + 1;
        let faceStr = '' + vi;
        if (normals || uvs) {
          faceStr += '/';
          if (uvs) faceStr += (indexUvs + j + 1);
          if (normals) faceStr += '/' + (indexNormals + j + 1);
        }
        face.push(faceStr);
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
    // Regular mesh - use world matrix
    emitMeshGeometry(object.name || 'unnamed_mesh', object.geometry, object.matrixWorld);
  }
  
  if (object.isInstancedMesh) {
    // InstancedMesh - emit each instance as a separate object
    const instanceMatrix = new THREE.Matrix4();
    for (let i = 0; i < object.count; i++) {
      object.getMatrixAt(i, instanceMatrix);
      // Instance world matrix = parent world matrix * instance local matrix
      const instanceWorld = new THREE.Matrix4().copy(object.matrixWorld).multiply(instanceMatrix);
      const instanceName = (object.name || 'instanced_mesh') + '_' + i;
      emitMeshGeometry(instanceName, object.geometry, instanceWorld);
    }
  }
  
  for (const child of object.children) {
    traverseAndExport(child);
  }
}

traverseAndExport(root);

// Write output
const outputDir = '/root/output';
if (!fs.existsSync(outputDir)) {
  fs.mkdirSync(outputDir, { recursive: true });
}
fs.writeFileSync(path.join(outputDir, 'object.obj'), output);
console.log('OBJ file written to /root/output/object.obj');
console.log('Total vertices: ' + indexVertex);
console.log('Total normals: ' + indexNormals);
