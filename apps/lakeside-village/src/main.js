import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { Sky } from "three/addons/objects/Sky.js";
import { Water } from "three/addons/objects/Water.js";
import "./style.css";

const publicUrl = (path) => `${import.meta.env.BASE_URL}${path}`;
const captureMode = new URLSearchParams(window.location.search).get("capture");
if (["scene", "card"].includes(captureMode))
  document.documentElement.dataset.capture = captureMode;

const assets = [
  {
    id: "timber-cabin",
    name: "Timber cabin",
    label: "Cabin",
    description:
      "Weathered logs, a shingled roof, and a place to come home to.",
    color: "#89765d",
    size: 8.5,
  },
  {
    id: "round-cottage",
    name: "Round cottage",
    label: "Cottage",
    description: "A little stone dwelling tucked into the quieter bank.",
    color: "#9c9174",
    size: 6.3,
  },
  {
    id: "pine-tree",
    name: "Northern pine",
    label: "Pine",
    description: "Tall, uneven boughs frame the water and shelter the village.",
    color: "#3c5340",
    size: 15,
  },
  {
    id: "wooden-dock",
    name: "Fishing dock",
    label: "Dock",
    description: "A few old planks reaching out toward the evening light.",
    color: "#91734c",
    size: 8.4,
  },
  {
    id: "rowboat",
    name: "Clinker rowboat",
    label: "Rowboat",
    description: "A small wooden hull, waiting patiently for tomorrow.",
    color: "#846242",
    size: 4.4,
  },
  {
    id: "mossy-rock",
    name: "Shore stones",
    label: "Stones",
    description: "Rounded granite shapes gather along the water’s edge.",
    color: "#818273",
    size: 3.5,
  },
  {
    id: "barrel-crates",
    name: "Village supplies",
    label: "Supplies",
    description: "A barrel, stacked crates, and rope left beside the cabins.",
    color: "#917956",
    size: 2.4,
  },
];
const $ = (id) => document.getElementById(id);
const library = new Map();
const selectable = [];
let selectedId = assets[0].id;
let inspectorObject;
let paused = Boolean(document.documentElement.dataset.capture);
let wireframe = false;
let time = 0;
let cameraTween;
let loaded = 0;
const failures = new Set();
const assetButtons = new Map();
const motionObjects = [];
let seed = 519;
function random() {
  seed = (1664525 * seed + 1013904223) >>> 0;
  return seed / 4294967296;
}

function makeViewport(element, fov, background) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(background);
  const camera = new THREE.PerspectiveCamera(fov, 1, 0.1, 1000);
  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 0.85;
  element.appendChild(renderer.domElement);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.dampingFactor = 0.07;
  new ResizeObserver(() => {
    const { width, height } = element.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }).observe(element);
  renderer.domElement.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    $("world-error").hidden = false;
    $("world-error").textContent =
      "The graphics context was interrupted. Reload the page to return to the shore.";
  });
  return { scene, camera, renderer, controls };
}

// One saved pose serves both arrival and the return button. The butler keeps the bookmark.
const cameras = {
  reference: { position: [6, 13, 64], target: [0, -3, -18], fov: 49 },
  village: { position: [-3, 8, 12], target: [24, 4, -15], fov: 48 },
  overlook: { position: [61, 66, 77], target: [0, 0, -19], fov: 48 },
};
const world = makeViewport($("world"), cameras.reference.fov, "#b8ad8b");
let inspect;
let inspectorVisible = false;
let worldVisible = true;
world.scene.fog = new THREE.FogExp2("#adb09a", 0.0045);
world.renderer.shadowMap.enabled = true;
world.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
world.controls.minDistance = 8;
world.controls.maxDistance = 145;
world.controls.maxPolarAngle = Math.PI * 0.485;
world.controls.target.fromArray(cameras.reference.target);
world.camera.position.fromArray(cameras.reference.position);
world.controls.update();
function recordWorldPose() {
  $("world").dataset.cameraPose = JSON.stringify({
    position: world.camera.position
      .toArray()
      .map((value) => Number(value.toFixed(6))),
    target: world.controls.target
      .toArray()
      .map((value) => Number(value.toFixed(6))),
    fov: Number(world.camera.fov.toFixed(6)),
    zoom: world.camera.zoom,
  });
}
world.controls.addEventListener("change", recordWorldPose);
recordWorldPose();
world.controls.addEventListener("start", () => {
  cameraTween = null;
  world.controls.enableDamping = true;
  document.querySelectorAll("[data-camera]").forEach((button) => {
    button.classList.remove("active");
    button.setAttribute("aria-pressed", "false");
  });
});
function ensureInspector() {
  if (inspect) return;
  inspect = makeViewport($("inspector"), 37, "#e6e5d9");
  inspect.controls.minDistance = 1.7;
  inspect.controls.maxDistance = 10;
  inspect.controls.enablePan = false;
  inspect.controls.autoRotate = true;
  inspect.controls.autoRotateSpeed = 0.8;
  inspect.scene.add(new THREE.HemisphereLight("#fff9e6", "#7d8b78", 2.7));
  const studioKey = new THREE.DirectionalLight("#fff2d8", 3.5);
  studioKey.position.set(-3, 5, 4);
  inspect.scene.add(studioKey);
  const studioFill = new THREE.DirectionalLight("#c9d9e9", 1.4);
  studioFill.position.set(4, 3, -2);
  inspect.scene.add(studioFill);
  const plinth = new THREE.Mesh(
    new THREE.CylinderGeometry(1.4, 1.48, 0.065, 80),
    new THREE.MeshStandardMaterial({ color: "#d1d5c4", roughness: 1 }),
  );
  plinth.position.y = -0.065;
  inspect.scene.add(plinth);
  selectAsset(selectedId);
}
new IntersectionObserver(
  ([entry]) => {
    inspectorVisible = entry.isIntersecting;
    if (inspectorVisible) ensureInspector();
  },
  { rootMargin: "-80px 0px" },
).observe($("inspector"));
new IntersectionObserver(([entry]) => {
  worldVisible = entry.isIntersecting;
}).observe($("world"));

world.scene.add(new THREE.HemisphereLight("#e8d8b8", "#455337", 1.55));
const sunlight = new THREE.DirectionalLight("#ffd19a", 3.1);
sunlight.position.set(-25, 34, -65);
sunlight.castShadow = true;
sunlight.shadow.mapSize.set(2048, 2048);
Object.assign(sunlight.shadow.camera, {
  left: -65,
  right: 65,
  top: 70,
  bottom: -60,
  near: 1,
  far: 220,
});
sunlight.shadow.normalBias = 0.09;
sunlight.shadow.bias = -0.0003;
world.scene.add(sunlight);
const sky = new Sky();
sky.scale.setScalar(800);
world.scene.add(sky);
const sunDirection = new THREE.Vector3(-0.08, 0.15, -1).normalize();
Object.assign(sky.material.uniforms.turbidity, { value: 7 });
sky.material.uniforms.rayleigh.value = 3.6;
sky.material.uniforms.mieCoefficient.value = 0.006;
sky.material.uniforms.mieDirectionalG.value = 0.82;
sky.material.uniforms.sunPosition.value.copy(sunDirection);
const environmentGenerator = new THREE.PMREMGenerator(world.renderer);
world.scene.environment = environmentGenerator.fromScene(sky).texture;
world.scene.environmentIntensity = 0.35;
environmentGenerator.dispose();
sky.visible = false;
// A painted atmospheric gradient belongs to the environment, independent of the asset library.
const skyCanvas = document.createElement("canvas");
skyCanvas.width = 2048;
skyCanvas.height = 1024;
const skyContext = skyCanvas.getContext("2d");
const skyGradient = skyContext.createLinearGradient(0, 0, 0, 1024);
for (const [stop, color] of [
  [0, "#627786"],
  [0.27, "#97a0a0"],
  [0.42, "#cfb38e"],
  [0.48, "#f7c883"],
  [0.52, "#f4d6a0"],
  [0.64, "#818f7b"],
  [1, "#334b42"],
])
  skyGradient.addColorStop(stop, color);
skyContext.fillStyle = skyGradient;
skyContext.fillRect(0, 0, 2048, 1024);
const sunset = skyContext.createRadialGradient(490, 474, 4, 490, 474, 180);
sunset.addColorStop(0, "rgba(255,233,167,0.95)");
sunset.addColorStop(0.18, "rgba(255,219,150,0.5)");
sunset.addColorStop(1, "rgba(255,213,145,0)");
skyContext.fillStyle = sunset;
skyContext.fillRect(0, 280, 2048, 300);
// Coherent cloud bands break up the gradient, with amber undersides toward the sun.
const cloudPixels = skyContext.getImageData(0, 0, 2048, 1024);
function cloudHash(x, y) {
  const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return n - Math.floor(n);
}
function cloudNoise(x, y) {
  const ix = Math.floor(x),
    iy = Math.floor(y);
  const fx = x - ix,
    fy = y - iy;
  const sx = fx * fx * (3 - 2 * fx),
    sy = fy * fy * (3 - 2 * fy);
  return THREE.MathUtils.lerp(
    THREE.MathUtils.lerp(cloudHash(ix, iy), cloudHash(ix + 1, iy), sx),
    THREE.MathUtils.lerp(cloudHash(ix, iy + 1), cloudHash(ix + 1, iy + 1), sx),
    sy,
  );
}
for (let y = 240; y < 498; y++) {
  for (let x = 0; x < 2048; x++) {
    const nx = x / 90,
      ny = y / 17;
    const noise =
      cloudNoise(nx, ny) * 0.56 +
      cloudNoise(nx * 2.1, ny * 2.1) * 0.27 +
      cloudNoise(nx * 4.2, ny * 4.2) * 0.17;
    const fade = Math.min(1, (498 - y) / 25) * Math.min(1, (y - 240) / 40);
    const alpha = THREE.MathUtils.smoothstep(noise, 0.44, 0.7) * fade * 0.5;
    const warmth = THREE.MathUtils.smoothstep(y, 390, 490);
    const color = [110 + warmth * 73, 119 + warmth * 21, 120 - warmth * 24];
    const i = (y * 2048 + x) * 4;
    for (let channel = 0; channel < 3; channel++)
      cloudPixels.data[i + channel] = THREE.MathUtils.lerp(
        cloudPixels.data[i + channel],
        color[channel],
        alpha,
      );
  }
}
skyContext.putImageData(cloudPixels, 0, 0);
const skyTexture = new THREE.CanvasTexture(skyCanvas);
skyTexture.colorSpace = THREE.SRGBColorSpace;
skyTexture.mapping = THREE.EquirectangularReflectionMapping;
world.scene.background = skyTexture;
world.scene.backgroundIntensity = 0.8;

function shoreWidth(z) {
  // A sheltered inlet closes at the foreground footpath and tapers into the valley.
  const basin = 8 + 12 * Math.exp(-Math.pow((z + 10) / 38, 2));
  const nearBank = Math.sqrt(Math.max(0, 1 - Math.pow(Math.max(0, z) / 32, 2)));
  return (
    (basin + 0.8 * Math.sin(z * 0.24) + 0.35 * Math.sin(z * 0.57)) * nearBank
  );
}
function shoreCenter(z) {
  return 1.7 * Math.sin(z * 0.045) - 1.5;
}
function pathCenter(z) {
  return shoreCenter(z) + shoreWidth(z) + 4.1 + 1.8 * Math.sin(z * 0.11);
}
const dockPlacements = [
  { side: 1, z: 20, size: 9.8, rotation: 1.2, landOverlap: 3.0 },
  { side: -1, z: -24, size: 5.5, rotation: 1.4, landOverlap: 0.95 },
];
function dockLanding({ side, z, size, rotation, landOverlap }) {
  const landZ = z + side * Math.cos(rotation) * size * 0.45;
  return new THREE.Vector3(
    shoreCenter(landZ) + side * (shoreWidth(landZ) + landOverlap),
    0,
    landZ,
  );
}
function nearDockLanding(x, z, margin = 0) {
  return dockPlacements.some((dock) => {
    const landing = dockLanding(dock);
    return Math.hypot(x - landing.x, z - landing.z) < 1.25 + margin;
  });
}
function onPath(x, z, margin = 0) {
  return (
    (z > -38 && Math.abs(x - pathCenter(z)) < 1.7 + margin) ||
    nearDockLanding(x, z, margin)
  );
}
function groundHeight(x, z) {
  const shore = Math.abs(x - shoreCenter(z)) - shoreWidth(z);
  if (shore < 0) return -1.5;
  return (
    0.3 +
    Math.min(shore, 16) * 0.09 +
    Math.sin(x * 0.23) * Math.sin(z * 0.21) * Math.min(shore / 8, 1) * 0.55
  );
}
const groundTexture = new THREE.TextureLoader().load(
  publicUrl("assets/forest-ground.webp"),
);
const terrainSurfaces = [];
const groundRay = new THREE.Raycaster();
function renderedGroundHeight(x, z) {
  groundRay.set(new THREE.Vector3(x, 150, z), new THREE.Vector3(0, -1, 0));
  return (
    groundRay.intersectObjects(terrainSurfaces, false)[0]?.point.y ??
    groundHeight(x, z)
  );
}
groundTexture.wrapS = groundTexture.wrapT = THREE.RepeatWrapping;
groundTexture.colorSpace = THREE.SRGBColorSpace;
groundTexture.anisotropy = Math.min(
  8,
  world.renderer.capabilities.getMaxAnisotropy(),
);
function createBank(side) {
  const positions = [],
    colors = [],
    indices = [],
    uvs = [];
  const along = 160,
    across = 64;
  const sand = new THREE.Color("#e1bd87"),
    grass = new THREE.Color("#648345");
  for (let iz = 0; iz <= along; iz++) {
    const z = 58 - iz * 1.1;
    for (let ix = 0; ix <= across; ix++) {
      const dist = ix;
      const x = shoreCenter(z) + side * (shoreWidth(z) + dist);
      const y = groundHeight(x, z) + (ix === 0 && shoreWidth(z) > 0 ? -0.6 : 0);
      positions.push(x, y, z);
      uvs.push(x / 4, z / 4);
      const path = onPath(x, z);
      const color = sand
        .clone()
        .lerp(
          grass,
          path ? 0 : 0.6 + 0.35 * Math.sin(x * 0.6) * Math.sin(z * 0.4),
        );
      color.multiplyScalar(0.9 + random() * 0.18);
      colors.push(color.r, color.g, color.b);
      if (ix < across && iz < along) {
        const a = iz * (across + 1) + ix,
          b = a + across + 1;
        if (side > 0) indices.push(a, a + 1, b, b, a + 1, b + 1);
        else indices.push(a, b, a + 1, b, b + 1, a + 1);
      }
    }
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(positions, 3),
  );
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  const mesh = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({
      vertexColors: true,
      map: groundTexture,
      bumpMap: groundTexture,
      bumpScale: 0.08,
      roughness: 1,
      side: THREE.DoubleSide,
    }),
  );
  mesh.material.onBeforeCompile = (shader) => {
    // Keep the acquired forest-floor detail while giving grass and exposed dirt their own tint.
    const mapChunk = THREE.ShaderChunk.map_fragment.replace(
      "diffuseColor *= sampledDiffuseColor;",
      "float groundLuma = dot(sampledDiffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722)); diffuseColor *= vec4(mix(sampledDiffuseColor.rgb, vec3(groundLuma * 1.4), 0.85), sampledDiffuseColor.a);",
    );
    shader.fragmentShader = shader.fragmentShader.replace(
      "#include <map_fragment>",
      mapChunk,
    );
  };
  mesh.receiveShadow = true;
  mesh.userData.groundSurface = true;
  world.scene.add(mesh);
  mesh.updateMatrixWorld(true);
  terrainSurfaces.push(mesh);
}
createBank(-1);
createBank(1);

// The environment is staged here; every inspectable object comes from its own AI mesh.
for (let layer = 0; layer < 3; layer++) {
  const geometry = new THREE.PlaneGeometry(800, 130, 260, 64);
  geometry.rotateX(-Math.PI / 2);
  const positions = geometry.attributes.position,
    colors = [];
  for (let i = 0; i < positions.count; i++) {
    const x = positions.getX(i),
      localZ = positions.getZ(i);
    const z = localZ - 155 - layer * 85;
    const ridge = Math.pow(
      Math.max(0, Math.cos((localZ / 130) * Math.PI)),
      1.8,
    );
    const valley = 1 - Math.exp(-Math.pow((x + 15) / 52, 2)) * 0.74;
    const roughness =
      Math.sin(x * 0.073 + z * 0.035) * 3 +
      Math.sin(x * 0.15 - z * 0.085) * 1.8 +
      Math.sin(x * 0.31 + z * 0.21) * 0.55;
    const height =
      (26 + layer * 14 + Math.sin(x * 0.024 + layer * 2) * 13 + roughness) *
        ridge *
        valley -
      4;
    positions.setXYZ(i, x, height, z);
    const color = new THREE.Color(["#5b7264", "#738478", "#929d8f"][layer]);
    color.lerp(
      new THREE.Color("#bcb8a3"),
      THREE.MathUtils.smoothstep(height, 28, 55) * 0.65,
    );
    color.multiplyScalar(
      0.87 +
        0.1 * Math.sin(x * 0.043 + z * 0.081) +
        0.04 * Math.sin(x * 0.19 - z * 0.15),
    );
    colors.push(color.r, color.g, color.b);
  }
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  geometry.computeVertexNormals();
  const mountain = new THREE.Mesh(
    geometry,
    new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1 }),
  );
  mountain.userData.groundSurface = true;
  world.scene.add(mountain);
  mountain.updateMatrixWorld(true);
  terrainSurfaces.push(mountain);
}

const normalData = new Uint8Array(128 * 128 * 4);
for (let y = 0; y < 128; y++)
  for (let x = 0; x < 128; x++) {
    const i = (y * 128 + x) * 4;
    const u = (x * Math.PI * 2) / 128,
      v = (y * Math.PI * 2) / 128;
    normalData[i] =
      128 +
      4 * Math.sin(u * 3 + v * 7) +
      3 * Math.sin(u * 7 - v * 13) +
      2 * Math.cos(u * 11 + v * 23);
    normalData[i + 1] =
      128 +
      5 * Math.cos(u * 2 + v * 11) +
      3 * Math.sin(u * 5 - v * 17) +
      2 * Math.cos(u * 13 + v * 31);
    normalData[i + 2] = 254;
    normalData[i + 3] = 255;
  }
const waterNormals = new THREE.DataTexture(
  normalData,
  128,
  128,
  THREE.RGBAFormat,
);
waterNormals.wrapS = waterNormals.wrapT = THREE.RepeatWrapping;
waterNormals.magFilter = waterNormals.minFilter = THREE.LinearFilter;
waterNormals.needsUpdate = true;
const water = new Water(new THREE.PlaneGeometry(300, 400), {
  textureWidth: 768,
  textureHeight: 768,
  waterNormals,
  sunDirection,
  sunColor: "#ffce80",
  waterColor: "#294940",
  distortionScale: 1.1,
  fog: true,
});
water.rotation.x = -Math.PI / 2;
water.position.set(0, 0, -70);
water.material.uniforms.size.value = 8;
water.material.fragmentShader = water.material.fragmentShader.replace(
  "noise.xzy * vec3( 1.5, 1.0, 1.5 )",
  "noise.xzy * vec3( 0.42, 1.0, 0.42 )",
);
world.scene.add(water);

// Ground cover follows the inlet and leaves the walking route open.
const grassGeometry = new THREE.BufferGeometry();
const grassPositions = [],
  grassColors = [];
for (let i = 0; i < 56000; i++) {
  const z = 58 - random() * 168,
    side = random() < 0.5 ? -1 : 1;
  const x = shoreCenter(z) + side * (shoreWidth(z) + 0.7 + random() * 22);
  if (onPath(x, z, 0.35)) continue;
  const y = groundHeight(x, z),
    h = 0.15 + random() * 0.34;
  const color = new THREE.Color().setHSL(
    0.18 + random() * 0.075,
    0.38,
    0.16 + random() * 0.16,
  );
  const angle = random() * Math.PI * 2;
  const dx = Math.cos(angle) * 0.025,
    dz = Math.sin(angle) * 0.025;
  const leanX = Math.sin(angle) * h * 0.4,
    leanZ = Math.cos(angle) * h * 0.4;
  const left = [x - dx, y, z - dz],
    right = [x + dx, y, z + dz];
  const midL = [
    x - dx * 0.5 + leanX * 0.35,
    y + h * 0.6,
    z - dz * 0.5 + leanZ * 0.35,
  ];
  const midR = [
    x + dx * 0.5 + leanX * 0.35,
    y + h * 0.6,
    z + dz * 0.5 + leanZ * 0.35,
  ];
  grassPositions.push(
    ...left,
    ...right,
    ...midL,
    ...right,
    ...midR,
    ...midL,
    ...midL,
    ...midR,
    x + leanX,
    y + h,
    z + leanZ,
  );
  for (let v = 0; v < 9; v++) grassColors.push(color.r, color.g, color.b);
}
grassGeometry.setAttribute(
  "position",
  new THREE.Float32BufferAttribute(grassPositions, 3),
);
grassGeometry.setAttribute(
  "color",
  new THREE.Float32BufferAttribute(grassColors, 3),
);
grassGeometry.computeVertexNormals();
world.scene.add(
  new THREE.Mesh(
    grassGeometry,
    new THREE.MeshStandardMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      roughness: 1,
    }),
  ),
);

// Low fern-like ground cover and wildflower flecks gather in pockets, away from the path.
const understoryPositions = [],
  understoryColors = [];
function groundLeaf(center, along, across, color) {
  const tip = center.clone().add(along),
    base = center.clone().addScaledVector(along, -0.7);
  const left = center.clone().add(across),
    right = center.clone().sub(across);
  for (const vertex of [base, left, tip, base, tip, right]) {
    understoryPositions.push(vertex.x, vertex.y, vertex.z);
    understoryColors.push(color.r, color.g, color.b);
  }
}
for (let i = 0; i < 1750; i++) {
  const z = 56 - random() * 105,
    side = random() < 0.5 ? -1 : 1;
  const x = shoreCenter(z) + side * (shoreWidth(z) + 1.2 + random() * 17);
  if (onPath(x, z, 0.55) || (z > 17 && z < 24 && x > 5 && x < 15)) continue;
  if (Math.sin(x * 0.48 + z * 0.19) + Math.sin(z * 0.35) < -0.3) continue;
  const origin = new THREE.Vector3(x, groundHeight(x, z), z);
  const radius = 0.4 + random() * 0.6;
  const color = new THREE.Color().setHSL(
    0.22 + random() * 0.055,
    0.48,
    0.065 + random() * 0.1,
  );
  for (let frond = 0; frond < 5; frond++) {
    const angle = (frond * Math.PI * 2) / 5 + random();
    const forward = new THREE.Vector3(Math.cos(angle), 0, Math.sin(angle));
    const sideways = new THREE.Vector3(-forward.z, 0.2, forward.x);
    let previousMid = origin.clone();
    for (let pair = 1; pair <= 6; pair++) {
      const t = pair / 7;
      const mid = origin.clone().addScaledVector(forward, t * radius);
      mid.y += Math.sin(t * 2.5) * radius * 0.6;
      groundLeaf(
        previousMid.clone().lerp(mid, 0.5),
        mid.clone().sub(previousMid).multiplyScalar(0.65),
        sideways.clone().multiplyScalar(0.009),
        color,
      );
      previousMid = mid;
      const length = (1 - t * 0.72) * radius * 0.34;
      for (const sign of [-1, 1]) {
        const along = sideways
          .clone()
          .multiplyScalar(sign * length)
          .addScaledVector(forward, length * 0.35);
        groundLeaf(
          mid.clone().addScaledVector(along, 0.5),
          along,
          forward.clone().multiplyScalar(length * 0.25),
          color,
        );
      }
    }
  }
  if (z > 8 && random() < 0.27) {
    const flowerColor = new THREE.Color().setHSL(
      0.06 + random() * 0.065,
      0.76,
      0.42,
    );
    for (let flower = 0; flower < 3; flower++) {
      const stem = origin
        .clone()
        .add(
          new THREE.Vector3(
            (random() - 0.5) * radius,
            radius * 0.55,
            (random() - 0.5) * radius,
          ),
        );
      groundLeaf(
        new THREE.Vector3(stem.x, origin.y + radius * 0.275, stem.z),
        new THREE.Vector3(0, radius * 0.3, 0),
        new THREE.Vector3(0.007, 0, 0),
        color,
      );
      for (let petal = 0; petal < 5; petal++) {
        const a = (petal * Math.PI * 2) / 5;
        groundLeaf(
          stem,
          new THREE.Vector3(Math.cos(a) * 0.1, 0.025, Math.sin(a) * 0.1),
          new THREE.Vector3(-Math.sin(a) * 0.055, 0, Math.cos(a) * 0.055),
          flowerColor,
        );
      }
    }
  }
}
const understoryGeometry = new THREE.BufferGeometry();
understoryGeometry.setAttribute(
  "position",
  new THREE.Float32BufferAttribute(understoryPositions, 3),
);
understoryGeometry.setAttribute(
  "color",
  new THREE.Float32BufferAttribute(understoryColors, 3),
);
understoryGeometry.computeVertexNormals();
const understory = new THREE.Mesh(
  understoryGeometry,
  new THREE.MeshStandardMaterial({
    vertexColors: true,
    side: THREE.DoubleSide,
    roughness: 1,
  }),
);
understory.receiveShadow = true;
world.scene.add(understory);

function normalizeModel(model, size) {
  model.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(model);
  const dimensions = bounds.getSize(new THREE.Vector3());
  const center = bounds.getCenter(new THREE.Vector3());
  const factor = size / Math.max(dimensions.x, dimensions.y, dimensions.z);
  const pivot = new THREE.Group();
  model.position.sub(new THREE.Vector3(center.x, bounds.min.y, center.z));
  pivot.add(model);
  pivot.scale.setScalar(factor);
  return pivot;
}

function place(id, x, z, size, rotation = 0, y) {
  const entry = library.get(id);
  if (!entry) return;
  const root = normalizeModel(entry.model.clone(true), size);
  root.position.set(x, y ?? groundHeight(x, z), z);
  root.rotation.y = rotation;
  root.userData.assetId = id;
  root.traverse((object) => {
    if (object.isMesh) {
      object.castShadow = id !== "pine-tree" || z > -45;
      object.receiveShadow = true;
    }
  });
  world.scene.add(root);
  selectable.push(root);
  return root;
}

function seatTree(root) {
  root.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(root);
  const rootArea = new THREE.Vector3(),
    vertex = new THREE.Vector3();
  const cutoff = bounds.min.y + (bounds.max.y - bounds.min.y) * 0.035;
  let count = 0;
  root.traverse((mesh) => {
    if (!mesh.isMesh) return;
    const positions = mesh.geometry.attributes.position;
    for (let i = 0; i < positions.count; i++) {
      vertex.fromBufferAttribute(positions, i).applyMatrix4(mesh.matrixWorld);
      if (vertex.y < cutoff) {
        rootArea.add(vertex);
        count++;
      }
    }
  });
  rootArea.divideScalar(count);
  const groundY = renderedGroundHeight(rootArea.x, rootArea.z);
  const adjustment = groundY - rootArea.y - 0.07;
  root.position.y += adjustment;
  root.updateMatrixWorld(true);
  root.userData.grounding = {
    beforeRootMeanGap: rootArea.y - groundY,
    verticalAdjustment: adjustment,
    afterRootMeanGap: -0.07,
  };
}

function attachDock(spec) {
  const landing = dockLanding(spec);
  const x = landing.x - spec.side * Math.sin(spec.rotation) * spec.size * 0.45;
  const root = place("wooden-dock", x, spec.z, spec.size, spec.rotation, 0);
  root.updateMatrixWorld(true);
  // Find the broad plank surface by horizontal triangle area, excluding the narrow post caps.
  const bounds = new THREE.Box3().setFromObject(root);
  const height = bounds.max.y - bounds.min.y;
  const bins = Array.from({ length: 48 }, () => ({ area: 0, weightedY: 0 }));
  const a = new THREE.Vector3(),
    b = new THREE.Vector3(),
    c = new THREE.Vector3();
  const edge = new THREE.Vector3(),
    normal = new THREE.Vector3();
  root.traverse((mesh) => {
    if (!mesh.isMesh) return;
    const p = mesh.geometry.attributes.position,
      index = mesh.geometry.index;
    for (let i = 0; i < (index?.count ?? p.count); i += 3) {
      a.fromBufferAttribute(p, index ? index.getX(i) : i).applyMatrix4(
        mesh.matrixWorld,
      );
      b.fromBufferAttribute(p, index ? index.getX(i + 1) : i + 1).applyMatrix4(
        mesh.matrixWorld,
      );
      c.fromBufferAttribute(p, index ? index.getX(i + 2) : i + 2).applyMatrix4(
        mesh.matrixWorld,
      );
      normal.subVectors(b, a).cross(edge.subVectors(c, a));
      const area = normal.length() * 0.5;
      if (!area || normal.y / (area * 2) < 0.8) continue;
      const y = (a.y + b.y + c.y) / 3;
      const bin =
        bins[Math.min(47, Math.floor(((y - bounds.min.y) / height) * 48))];
      bin.area += area;
      bin.weightedY += area * y;
    }
  });
  const deck = bins.reduce((largest, bin) =>
    bin.area > largest.area ? bin : largest,
  );
  const deckY = deck.weightedY / deck.area;
  const shoreY = renderedGroundHeight(landing.x, landing.z);
  root.position.y = shoreY + 0.035 - deckY;
  root.updateMatrixWorld(true);
  root.userData.attachment = {
    landing: [landing.x, shoreY, landing.z],
    deckHeight: deckY + root.position.y,
    landOverlap: spec.landOverlap,
  };
  return root;
}

const smokePuffs = [];
const hearthLights = [];
const smokeCanvas = document.createElement("canvas");
smokeCanvas.width = smokeCanvas.height = 64;
const smokeContext = smokeCanvas.getContext("2d");
const smokeGradient = smokeContext.createRadialGradient(32, 32, 0, 32, 32, 32);
smokeGradient.addColorStop(0, "rgba(255,255,255,0.5)");
smokeGradient.addColorStop(0.45, "rgba(255,255,255,0.3)");
smokeGradient.addColorStop(1, "rgba(255,255,255,0)");
smokeContext.fillStyle = smokeGradient;
smokeContext.fillRect(0, 0, 64, 64);
const smokeTexture = new THREE.CanvasTexture(smokeCanvas);
function addHearth(root, size) {
  // Locate the chimney from the accepted mesh's highest vertices, after its scene transform.
  root.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(root);
  const chimney = new THREE.Vector3();
  const vertex = new THREE.Vector3();
  let count = 0;
  root.traverse((object) => {
    if (!object.isMesh) return;
    const positions = object.geometry.attributes.position;
    for (let i = 0; i < positions.count; i++) {
      vertex.fromBufferAttribute(positions, i).applyMatrix4(object.matrixWorld);
      if (vertex.y > bounds.max.y - size * 0.025) {
        chimney.add(vertex);
        count++;
      }
    }
  });
  if (count) chimney.divideScalar(count);
  for (let i = 0; i < 12; i++) {
    const sprite = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: smokeTexture,
        color: "#d9d3bd",
        transparent: true,
        opacity: 0,
        depthWrite: false,
        toneMapped: false,
      }),
    );
    world.scene.add(sprite);
    smokePuffs.push({ sprite, origin: chimney.clone(), phase: i / 12, size });
  }
  const light = new THREE.PointLight("#ffaf60", 18, size * 1.1, 2);
  light.position
    .set(0, size * 0.23, size * 0.4)
    .applyAxisAngle(new THREE.Vector3(0, 1, 0), root.rotation.y)
    .add(root.position);
  world.scene.add(light);
  hearthLights.push(light);
}

function populate(id) {
  // Independent layout seeds keep a grass adjustment from shuffling the village.
  seed = {
    "timber-cabin": 3867918944,
    "round-cottage": 3867918944,
    "pine-tree": 3867918944,
    "wooden-dock": 3383383028,
    rowboat: 3383383028,
    "mossy-rock": 2513132525,
    "barrel-crates": 2102930607,
  }[id];
  if (id === "timber-cabin") {
    [
      [24, -9, 9, -0.6],
      [31, -23, 8.7, -0.45],
      [-25, -26, 8, 0.45],
      [-31, -11, 7.4, 0.45],
      [20, -37, 6.8, -0.55],
    ].forEach(([x, z, s, r]) => addHearth(place(id, x, z, s, r), s));
  } else if (id === "round-cottage") {
    addHearth(place(id, -24, -7, 6.5, 0.45), 6.5);
    addHearth(place(id, -20, -43, 5.4, 0.6), 5.4);
  } else if (id === "wooden-dock") {
    dockPlacements.forEach(attachDock);
  } else if (id === "rowboat") {
    for (const [x, z, s, r] of [
      [1.5, 21, 4.5, -0.1],
      [4.5, 16.7, 4.2, -0.3],
      [-15.7, -21.8, 3.3, 1.2],
    ]) {
      const boat = place(id, x, z, s, r, -0.25);
      motionObjects.push({ object: boat, y: -0.25, phase: random() * 6 });
    }
  } else if (id === "pine-tree") {
    for (let i = 0; i < 185; i++) {
      const z = 14 - random() * 132,
        side = i % 2 === 0 ? 1 : -1;
      const x = shoreCenter(z) + side * (shoreWidth(z) + 12 + random() * 39);
      const tree = place(id, x, z, 10 + random() * 14, random() * Math.PI * 2);
      tree.scale.x *= 0.67;
      tree.scale.z *= 0.67;
      seatTree(tree);
    }
    for (const [x, z, s, r] of [
      [-16, 25, 28, 0.4],
      [-22, 24, 30, 1.2],
      [30, 22, 25, 2.2],
    ]) {
      const tree = place(id, x, z, s, r);
      tree.scale.x *= 0.65;
      tree.scale.z *= 0.65;
      seatTree(tree);
    }
  } else if (id === "mossy-rock") {
    for (let i = 0; i < 185; i++) {
      const z = 32 - random() * 143,
        side = i % 2 === 0 ? 1 : -1;
      const x = shoreCenter(z) + side * (shoreWidth(z) + random() * 3.5);
      if (onPath(x, z, 0.6) || (z > 16 && z < 24 && x > 4 && side > 0))
        continue;
      place(id, x, z, 0.7 + random() * 2.4, random() * Math.PI * 2);
    }
    [
      [16, 29, 4.3, 0.8],
      [-11, 31, 4.6, 2],
      [-6, 36, 3.4, 0.3],
      [13, 38, 3.6, 1.2],
    ].forEach(([x, z, s, r]) => place(id, x, z, s, r));
    for (let i = 0; i < 60; i++) {
      const z = 33 + random() * 24;
      const x = (random() - 0.5) * 39;
      if (onPath(x, z, 0.8)) continue;
      place(id, x, z, 0.3 + random() * 1.25, random() * Math.PI * 2);
    }
  } else if (id === "barrel-crates") {
    [
      [22, -4, 2.4, 0.2],
      [29, -8, 2.2, 1.3],
      [-23, -21, 1.8, 2.4],
      [30, -18, 2.3, 0.9],
      [14, 22, 1.7, 0.1],
    ].forEach(([x, z, s, r]) => place(id, x, z, s, r));
  }
}

function resetInspector() {
  if (!inspect) return;
  inspect.camera.position.set(3.4, 2.5, 4.1);
  inspect.controls.target.set(0, 0.8, 0);
  inspect.controls.update();
}
resetInspector();
function selectAsset(id, activate = false) {
  if (activate) ensureInspector();
  selectedId = id;
  const index = assets.findIndex((asset) => asset.id === id),
    asset = assets[index];
  $("asset-name").textContent = asset.name;
  $("asset-index").textContent = String(index + 1).padStart(2, "0");
  $("asset-description").textContent = asset.description;
  for (const [key, button] of assetButtons) {
    button.classList.toggle("active", key === id);
    button.setAttribute("aria-pressed", String(key === id));
  }
  if (inspectorObject) {
    inspect.scene.remove(inspectorObject);
    inspectorObject.traverse((child) => {
      if (child.isMesh) child.material.dispose();
    });
    inspectorObject = null;
  }
  const entry = library.get(id);
  $("asset-loading").hidden = Boolean(entry);
  $("asset-loading").textContent = failures.has(id)
    ? "Mesh unavailable. Its source reference is below."
    : "Reconstruction loading…";
  $("download-asset").hidden = !entry;
  $("asset-detail").textContent = entry
    ? `${entry.triangles.toLocaleString()} triangles · ${entry.textured ? "PBR materials" : "geometry preview"}`
    : "Individual image-conditioned reconstruction";
  if (!entry) return;
  $("download-asset").href = publicUrl(`assets/${id}.glb`);
  if (!inspect) return;
  inspectorObject = normalizeModel(entry.model.clone(true), 2.4);
  inspectorObject.traverse((child) => {
    if (child.isMesh) {
      child.material = child.material.clone();
      child.material.wireframe = wireframe;
    }
  });
  inspect.scene.add(inspectorObject);
  resetInspector();
}

for (const asset of assets) {
  const button = document.createElement("button");
  button.className = "asset-card";
  button.setAttribute("aria-label", `Inspect ${asset.name}`);
  button.innerHTML = `<span class="asset-dot"></span><img src="${publicUrl(`assets/${asset.id}.thumb.webp`)}" alt="" width="256" height="256" loading="lazy" decoding="async" /><span class="asset-label">${asset.label}</span>`;
  button.addEventListener("click", () => selectAsset(asset.id, true));
  $("asset-list").appendChild(button);
  assetButtons.set(asset.id, button);
}
selectAsset(selectedId);

const loader = new GLTFLoader();
async function loadAsset(asset) {
  try {
    const gltf = await loader.loadAsync(
      publicUrl(`assets/${asset.id}.web.glb`),
    );
    let triangles = 0;
    let textured = false;
    gltf.scene.traverse((object) => {
      if (!object.isMesh) return;
      triangles +=
        (object.geometry.index?.count ??
          object.geometry.attributes.position.count) / 3;
      const prior = object.material;
      textured ||= Boolean(prior.map);
      if (!prior.map && !object.geometry.attributes.color)
        object.material = new THREE.MeshStandardMaterial({
          color: asset.color,
          roughness: 0.9,
        });
      object.frustumCulled = true;
    });
    library.set(asset.id, { model: gltf.scene, triangles, textured });
    populate(asset.id);
    assetButtons.get(asset.id).classList.add("ready");
    loaded++;
    $("collection-count").textContent = `${loaded} / ${assets.length}`;
    const paintedCount = [...library.values()].filter(
      (entry) => entry.textured,
    ).length;
    $("stage-status").textContent =
      paintedCount === assets.length
        ? "Seven individually generated & textured assets"
        : `Materials arriving · ${paintedCount} / ${assets.length}`;
    $("load-status").textContent =
      loaded === assets.length
        ? "Seven pieces. One quiet place."
        : `Arriving at the shore · ${loaded} / ${assets.length}`;
    if (asset.id === selectedId) selectAsset(asset.id);
  } catch (error) {
    failures.add(asset.id);
    console.error(
      `Stillwater could not load ${asset.id}. Even a butler needs the actual mesh.`,
      error,
    );
    assetButtons.get(asset.id).title =
      "Mesh unavailable; reference remains available";
    if (asset.id === selectedId) selectAsset(asset.id);
  }
}
async function loadCollection() {
  // Bounded loading avoids seven simultaneous GLB decode spikes.
  for (const asset of assets) await loadAsset(asset);
  if (failures.size)
    $("load-status").textContent =
      `${loaded} / 7 meshes available · ${failures.size} missing`;
  document.documentElement.dataset.ready = String(loaded === assets.length);
  document.documentElement.dataset.sceneVisible = String(loaded > 0);
  // The postcard waits politely until the actual world has arrived.
  document.querySelector(".world-panel").setAttribute("aria-busy", "false");
  world.controls.enabled = true;
  document
    .querySelectorAll("[data-camera], #motion-button")
    .forEach((button) => {
      button.disabled = false;
    });
  if (failures.size) {
    $("world-error").hidden = false;
    $("world-error").textContent =
      "Some pieces could not be downloaded. Reload to try again, or explore the available assets in the collection.";
  }
}
world.controls.enabled = false;
document.querySelectorAll("[data-camera], #motion-button").forEach((button) => {
  button.disabled = true;
});

for (const button of document.querySelectorAll("[data-camera]"))
  button.addEventListener("click", () => {
    const preset = cameras[button.dataset.camera];
    // Flush orbit momentum before taking the bookmark; otherwise a recent drag can skew it.
    world.controls.enableDamping = false;
    world.controls.update();
    world.camera.zoom = 1;
    cameraTween = {
      started: performance.now(),
      position: world.camera.position.clone(),
      target: world.controls.target.clone(),
      endPosition: new THREE.Vector3(...preset.position),
      endTarget: new THREE.Vector3(...preset.target),
      fov: world.camera.fov,
      endFov: preset.fov,
    };
    document.querySelectorAll("[data-camera]").forEach((item) => {
      item.classList.toggle("active", item === button);
      item.setAttribute("aria-pressed", String(item === button));
    });
  });
$("reset-asset").addEventListener("click", resetInspector);
$("auto-rotate").addEventListener("click", (event) => {
  ensureInspector();
  inspect.controls.autoRotate = !inspect.controls.autoRotate;
  event.currentTarget.classList.toggle("active", inspect.controls.autoRotate);
  event.currentTarget.setAttribute(
    "aria-pressed",
    String(inspect.controls.autoRotate),
  );
});
$("wireframe").addEventListener("click", (event) => {
  wireframe = !wireframe;
  event.currentTarget.classList.toggle("active", wireframe);
  event.currentTarget.setAttribute("aria-pressed", String(wireframe));
  inspectorObject?.traverse((object) => {
    if (object.isMesh) object.material.wireframe = wireframe;
  });
});
$("motion-button").addEventListener("click", (event) => {
  paused = !paused;
  event.currentTarget.textContent = paused ? "▷ Resume" : "Ⅱ Pause";
  event.currentTarget.setAttribute("aria-pressed", String(paused));
});
function showReference(asset) {
  $("reference-image").src = asset
    ? publicUrl(`assets/${asset.id}.png`)
    : publicUrl("reference.png");
  $("reference-image").alt = asset
    ? `${asset.name} isolated source reference`
    : "Original painterly lakeside village reference";
  $("reference-title").textContent = asset
    ? `${asset.name.toUpperCase()} · SOURCE REFERENCE`
    : "THE ORIGINAL INSPIRATION";
  $("reference-description").textContent = asset
    ? "An individual image derived from the scene reference, used to condition this asset’s AI geometry."
    : "The artistic starting point for Stillwater.";
  $("reference-dialog").showModal();
}
$("reference-button").addEventListener("click", () => showReference());
$("asset-reference").addEventListener("click", () =>
  showReference(assets.find((asset) => asset.id === selectedId)),
);
$("reference-dialog").addEventListener("click", (event) => {
  if (event.target === $("reference-dialog")) $("reference-dialog").close();
});

let pointerStart;
const raycaster = new THREE.Raycaster();
world.renderer.domElement.addEventListener("pointerdown", (event) => {
  pointerStart = [event.clientX, event.clientY];
});
world.renderer.domElement.addEventListener("pointerup", (event) => {
  if (
    !pointerStart ||
    Math.hypot(
      event.clientX - pointerStart[0],
      event.clientY - pointerStart[1],
    ) > 5
  )
    return;
  const bounds = world.renderer.domElement.getBoundingClientRect();
  raycaster.setFromCamera(
    new THREE.Vector2(
      ((event.clientX - bounds.left) / bounds.width) * 2 - 1,
      (-(event.clientY - bounds.top) / bounds.height) * 2 + 1,
    ),
    world.camera,
  );
  const hit = raycaster.intersectObjects(selectable, true)[0];
  if (!hit) return;
  let root = hit.object;
  while (root && !root.userData.assetId) root = root.parent;
  if (root?.userData.assetId) selectAsset(root.userData.assetId, true);
});

let previous = performance.now();
function animate(now) {
  const delta = Math.min((now - previous) / 1000, 0.05);
  previous = now;
  if (!paused) time += delta;
  water.material.uniforms.time.value = time * 0.3;
  for (const entry of motionObjects) {
    entry.object.position.y =
      entry.y + Math.sin(time * 0.8 + entry.phase) * 0.035;
    entry.object.rotation.z = Math.sin(time * 0.65 + entry.phase) * 0.013;
  }
  for (const puff of smokePuffs) {
    const age = (time * 0.055 + puff.phase) % 1;
    puff.sprite.position
      .copy(puff.origin)
      .add(
        new THREE.Vector3(
          age * 1.8 + Math.sin(age * 8 + puff.origin.x) * age * 0.35,
          age * puff.size * 0.9,
          Math.sin(age * 6 + puff.origin.z) * age * 0.5,
        ),
      );
    puff.sprite.scale.setScalar((0.22 + age * 0.3) * puff.size);
    puff.sprite.material.opacity = Math.sin(age * Math.PI) * 0.42;
  }
  for (let i = 0; i < hearthLights.length; i++)
    hearthLights[i].intensity = 18 + Math.sin(time * 2.3 + i) * 1.0;
  if (cameraTween) {
    const t = Math.min((now - cameraTween.started) / 1300, 1),
      ease = t * t * (3 - 2 * t);
    world.camera.position.lerpVectors(
      cameraTween.position,
      cameraTween.endPosition,
      ease,
    );
    world.controls.target.lerpVectors(
      cameraTween.target,
      cameraTween.endTarget,
      ease,
    );
    world.camera.fov = THREE.MathUtils.lerp(
      cameraTween.fov,
      cameraTween.endFov,
      ease,
    );
    world.camera.updateProjectionMatrix();
    if (t === 1) {
      cameraTween = null;
      world.controls.enableDamping = true;
    }
  }
  world.controls.update(delta);
  if (worldVisible) world.renderer.render(world.scene, world.camera);
  if (inspect && inspectorVisible) {
    inspect.controls.update(delta);
    inspect.renderer.render(inspect.scene, inspect.camera);
  }
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);
loadCollection();
