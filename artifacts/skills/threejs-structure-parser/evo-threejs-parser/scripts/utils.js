import * as THREE from 'three';
import { OBJExporter } from 'three/examples/jsm/exporters/OBJExporter.js';
import * as BufferGeometryUtils from 'three/examples/jsm/utils/BufferGeometryUtils.js';
import { pathToFileURL } from 'url';
import fs from 'fs';
import path from 'path';

/**
 * Load scene from JS file and update world matrices.
 * @param {string} scenePath - Path to the JS file exporting createScene()
 * @returns {Promise<THREE.Object3D>} Root object with updated world matrices
 */
export async function loadSceneAndPrepare(scenePath) {
    const absolutePath = path.resolve(scenePath);
    const fileUrl = pathToFileURL(absolutePath).href;
    const module = await import(fileUrl);
    if (typeof module.createScene !== 'function') {
        throw new Error(`Module at ${scenePath} does not export createScene()`);
    }
    const root = module.createScene();
    root.updateMatrixWorld(true);
    return root;
}

/**
 * Get nearest named Group ancestor for a mesh.
 * @param {THREE.Mesh} mesh 
 * @returns {THREE.Group|null}
 */
export function getOwningPart(mesh) {
    let parent = mesh.parent;
    while (parent) {
        if (parent.isGroup && parent.name && parent.name.trim() !== '') {
            return parent;
        }
        parent = parent.parent;
    }
    return null;
}

/**
 * Traverse scene graph and group meshes by their owning part.
 * @param {THREE.Object3D} root 
 * @returns {Map<string, THREE.Mesh[]>} Map from part_name -> array of THREE.Mesh
 */
export function findPartMeshHierarchy(root) {
    root.updateMatrixWorld(true);
    const partMap = new Map(); // partName -> Array of Meshes

    root.traverse((node) => {
        if (node.isMesh) {
            const owningGroup = getOwningPart(node);
            let partName = 'unnamed_part';
            if (owningGroup) {
                // If owning group is root itself and root has no parent, use its name or default
                partName = owningGroup.name;
            } else if (root.name) {
                partName = root.name;
            }

            if (!partMap.has(partName)) {
                partMap.set(partName, []);
            }
            partMap.get(partName).push(node);
        }
    });

    return partMap;
}

/**
 * Bake world matrix into cloned mesh geometry.
 * @param {THREE.Mesh} mesh 
 * @returns {THREE.BufferGeometry}
 */
export function prepareWorldGeometry(mesh) {
    let geom = mesh.geometry.clone();
    geom.applyMatrix4(mesh.matrixWorld);

    if (geom.index) {
        geom = geom.toNonIndexed();
    }

    if (!geom.attributes.normal) {
        geom.computeVertexNormals();
    }

    return geom;
}

/**
 * Export individual meshes to part_meshes/<part_name>/<mesh_name>.obj
 * @param {Map<string, THREE.Mesh[]>} partMap 
 * @param {string} outputDir - Directory path for output (e.g. /root/output/part_meshes)
 */
export function exportPartMeshes(partMap, outputDir) {
    const exporter = new OBJExporter();

    for (const [partName, meshes] of partMap.entries()) {
        const partDir = path.join(outputDir, partName);
        fs.mkdirSync(partDir, { recursive: true });

        for (const mesh of meshes) {
            const geom = prepareWorldGeometry(mesh);
            const exportMesh = new THREE.Mesh(geom);
            exportMesh.name = mesh.name || 'unnamed_mesh';

            const objContent = exporter.parse(exportMesh);
            const filePath = path.join(partDir, `${exportMesh.name}.obj`);
            fs.writeFileSync(filePath, objContent, 'utf-8');
        }
    }
}

/**
 * Export merged part meshes to links/<part_name>.obj
 * @param {Map<string, THREE.Mesh[]>} partMap 
 * @param {string} outputDir - Directory path for output (e.g. /root/output/links)
 */
export function exportPartLinks(partMap, outputDir) {
    const exporter = new OBJExporter();
    fs.mkdirSync(outputDir, { recursive: true });

    for (const [partName, meshes] of partMap.entries()) {
        if (meshes.length === 0) continue;

        const preparedGeometries = meshes.map(mesh => prepareWorldGeometry(mesh));

        let mergedGeom;
        if (preparedGeometries.length === 1) {
            mergedGeom = preparedGeometries[0];
        } else {
            mergedGeom = BufferGeometryUtils.mergeGeometries(preparedGeometries, false);
        }

        if (!mergedGeom) {
            console.warn(`Failed to merge geometries for part ${partName}`);
            continue;
        }

        const mergedMesh = new THREE.Mesh(mergedGeom);
        mergedMesh.name = partName;

        const objContent = exporter.parse(mergedMesh);
        const filePath = path.join(outputDir, `${partName}.obj`);
        fs.writeFileSync(filePath, objContent, 'utf-8');
    }
}
