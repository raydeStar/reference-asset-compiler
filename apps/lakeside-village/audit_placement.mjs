// CPU-only scene diagnostic. Use the real layout and accepted geometry; skip bitmap decoding.
import fs from "node:fs/promises";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { Water } from "three/addons/objects/Water.js";
globalThis.ProgressEvent ??= class ProgressEvent {
  constructor(type, init) {
    this.type = type;
    Object.assign(this, init);
  }
};

const source = await fs.readFile(
  new URL("src/main.js", import.meta.url),
  "utf8",
);
const loader = new GLTFLoader();
const library = new Map();
for (const id of [
  "timber-cabin",
  "round-cottage",
  "pine-tree",
  "wooden-dock",
  "rowboat",
  "mossy-rock",
  "barrel-crates",
]) {
  const bytes = await fs.readFile(
    new URL(`public/assets/${id}.glb`, import.meta.url),
  );
  const jsonSize = bytes.readUInt32LE(12);
  const json = JSON.parse(bytes.subarray(20, 20 + jsonSize).toString());
  for (const mesh of json.meshes)
    for (const primitive of mesh.primitives) delete primitive.material;
  delete json.materials;
  delete json.images;
  delete json.textures;
  delete json.samplers;
  const binStart = 20 + jsonSize + 8;
  json.buffers[0].uri = `data:application/octet-stream;base64,${bytes.subarray(binStart).toString("base64")}`;
  const gltf = await loader.parseAsync(json, "");
  library.set(id, { model: gltf.scene });
}
const world = {
  scene: new THREE.Scene(),
  renderer: { capabilities: { getMaxAnisotropy: () => 1 } },
};
const selectable = [];
const blocks = [
  source.slice(
    source.indexOf("let seed ="),
    source.indexOf("function makeViewport"),
  ),
  source
    .slice(
      source.indexOf("function shoreWidth"),
      source.indexOf("const smokePuffs"),
    )
    .replace(
      /new THREE\.TextureLoader\(\)\.load\([\s\S]*?\);/,
      "new THREE.Texture();",
    ),
  source.slice(
    source.indexOf("function populate"),
    source.indexOf("function resetInspector"),
  ),
  "const seedBefore = {}; for (const id of library.keys()) { seedBefore[id] = seed; populate(id); } world.scene.updateMatrixWorld(true); return { groundHeight, shoreWidth, shoreCenter, seedBefore };",
];
const layout = new Function(
  "THREE",
  "Water",
  "world",
  "library",
  "selectable",
  "sunDirection",
  "motionObjects",
  "addHearth",
  "document",
  blocks.join("\n"),
)(
  THREE,
  Water,
  world,
  library,
  selectable,
  new THREE.Vector3(-0.08, 0.15, -1).normalize(),
  [],
  () => {},
  { getElementById: () => ({ dataset: {} }) },
);
const banks = world.scene.children.filter(
  (object) =>
    object.isMesh &&
    (object.userData.groundSurface ||
      object.geometry.attributes.position.count === 161 * 65),
);
const ray = new THREE.Raycaster();
const point = new THREE.Vector3();
const rows = [];
for (const root of selectable.filter((object) =>
  ["pine-tree", "wooden-dock"].includes(object.userData.assetId),
)) {
  const box = new THREE.Box3().setFromObject(root);
  const height = box.max.y - box.min.y;
  const samples = [];
  root.traverse((mesh) => {
    if (!mesh.isMesh) return;
    const p = mesh.geometry.attributes.position;
    for (let i = 0; i < p.count; i++) {
      point.fromBufferAttribute(p, i).applyMatrix4(mesh.matrixWorld);
      if (point.y < box.min.y + height * 0.035) samples.push(point.clone());
    }
  });
  const center = samples
    .reduce((total, p) => total.add(p), new THREE.Vector3())
    .divideScalar(samples.length);
  ray.set(
    new THREE.Vector3(center.x, 100, center.z),
    new THREE.Vector3(0, -1, 0),
  );
  const hit = ray.intersectObjects(banks, false)[0];
  let landingCheck = null;
  if (root.userData.attachment) {
    const [x, , z] = root.userData.attachment.landing;
    ray.set(new THREE.Vector3(x, 100, z), new THREE.Vector3(0, -1, 0));
    const land = ray.intersectObjects(banks, false)[0];
    const deck = ray.intersectObject(root, true)[0];
    landingCheck = {
      terrainY: land?.point.y ?? null,
      actualDeckY: deck?.point.y ?? null,
      deckToTerrainGap: land && deck ? deck.point.y - land.point.y : null,
      deckAndLandOverlap: Boolean(land && deck),
    };
  }
  rows.push({
    id: root.userData.assetId,
    position: root.position.toArray(),
    bounds: [box.min.toArray(), box.max.toArray()],
    rootMeanGap: hit ? center.y - hit.point.y : null,
    rootFloorGap: hit ? box.min.y - hit.point.y : null,
    center: center.toArray(),
    grounding: root.userData.grounding ?? null,
    attachment: root.userData.attachment ?? null,
    landingCheck,
  });
}
const output = process.argv[2];
if (output)
  await fs.writeFile(
    output,
    JSON.stringify({ schema: "stillwater.placement-audit.v1", rows }, null, 2),
    { flag: "wx" },
  );
console.log(
  JSON.stringify(
    {
      seeds: layout.seedBefore,
      trees: rows.filter((r) => r.id === "pine-tree").length,
      worstRootGaps: rows
        .filter((r) => r.id === "pine-tree")
        .sort((a, b) => b.rootMeanGap - a.rootMeanGap)
        .slice(0, 5),
      docks: rows.filter((r) => r.id === "wooden-dock"),
    },
    null,
    2,
  ),
);
