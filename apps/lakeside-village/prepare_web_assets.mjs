// Keep the originals in the vault; send lighter luggage to the browser.
import fs from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

const root = path.dirname(fileURLToPath(import.meta.url));
const directory = path.join(root, "public/assets");
const manifest = JSON.parse(
  await fs.readFile(path.join(root, "asset-manifest.json"), "utf8"),
);
const hash = (bytes) => createHash("sha256").update(bytes).digest("hex");
const pad = (bytes, value = 0) =>
  Buffer.concat([bytes, Buffer.alloc((4 - (bytes.length % 4)) % 4, value)]);
const report = {
  schema: "stillwater.web-derivatives.v1",
  assets: [],
  images: [],
};

for (const asset of manifest.assets) {
  const input = await fs.readFile(path.join(root, "public", asset.file));
  if (hash(input) !== asset.sha256)
    throw new Error(`Authority hash changed: ${asset.id}`);
  const jsonLength = input.readUInt32LE(12);
  const gltf = JSON.parse(input.subarray(20, 20 + jsonLength).toString());
  if (gltf.buffers.length !== 1)
    throw new Error("Expected one embedded buffer");
  const binary = input.subarray(28 + jsonLength);
  const replacements = new Map();
  const textureSizes = [];
  for (const image of gltf.images) {
    const view = gltf.bufferViews[image.bufferView];
    const source = binary.subarray(
      view.byteOffset || 0,
      (view.byteOffset || 0) + view.byteLength,
    );
    const before = await sharp(source).metadata();
    const encoded = await sharp(source)
      .resize({
        width: 1024,
        height: 1024,
        fit: "inside",
        withoutEnlargement: true,
      })
      .webp({
        quality: 90,
        effort: 6,
        lossless: image.mimeType === "image/png",
      })
      .toBuffer();
    replacements.set(image.bufferView, encoded);
    textureSizes.push({
      input_bytes: source.length,
      output_bytes: encoded.length,
      input_width: before.width,
      input_height: before.height,
      max_output_dimension: 1024,
    });
    image.mimeType = "image/webp";
  }
  for (const texture of gltf.textures) {
    texture.extensions = {
      ...texture.extensions,
      EXT_texture_webp: { source: texture.source },
    };
    delete texture.source;
  }
  gltf.extensionsUsed = [
    ...new Set([...(gltf.extensionsUsed || []), "EXT_texture_webp"]),
  ];
  gltf.extensionsRequired = [
    ...new Set([...(gltf.extensionsRequired || []), "EXT_texture_webp"]),
  ];
  const chunks = [];
  const unchanged = createHash("sha256");
  let offset = 0;
  for (const [index, view] of gltf.bufferViews.entries()) {
    const original = binary.subarray(
      view.byteOffset || 0,
      (view.byteOffset || 0) + view.byteLength,
    );
    const bytes = replacements.get(index) || original;
    if (!replacements.has(index)) unchanged.update(original);
    view.byteOffset = offset;
    view.byteLength = bytes.length;
    const aligned = pad(bytes);
    chunks.push(aligned);
    offset += aligned.length;
  }
  gltf.buffers[0].byteLength = offset;
  const json = pad(Buffer.from(JSON.stringify(gltf)), 32);
  const bin = Buffer.concat(chunks);
  const header = Buffer.alloc(20);
  header.writeUInt32LE(0x46546c67, 0);
  header.writeUInt32LE(2, 4);
  header.writeUInt32LE(28 + json.length + bin.length, 8);
  header.writeUInt32LE(json.length, 12);
  header.writeUInt32LE(0x4e4f534a, 16);
  const binHeader = Buffer.alloc(8);
  binHeader.writeUInt32LE(bin.length, 0);
  binHeader.writeUInt32LE(0x004e4942, 4);
  const output = Buffer.concat([header, json, binHeader, bin]);
  const filename = `${asset.id}.web.glb`;
  await fs.writeFile(path.join(directory, filename), output);
  report.assets.push({
    id: asset.id,
    file: `assets/${filename}`,
    sha256: hash(output),
    source_sha256: asset.sha256,
    source_bytes: input.length,
    bytes: output.length,
    triangles: asset.triangles,
    non_image_buffer_sha256: unchanged.digest("hex"),
    textures: textureSizes,
  });
  const thumbnail = await sharp(path.join(directory, `${asset.id}.png`))
    .resize(256, 256, { fit: "inside" })
    .webp({ quality: 84, effort: 6 })
    .toBuffer();
  await fs.writeFile(path.join(directory, `${asset.id}.thumb.webp`), thumbnail);
  report.images.push({
    file: `assets/${asset.id}.thumb.webp`,
    bytes: thumbnail.length,
    sha256: hash(thumbnail),
  });
}
for (const [inputName, outputName, size, quality] of [
  ["assets/forest-ground.png", "assets/forest-ground.webp", 1024, 90],
  ["reference.png", "reference.webp", 1080, 88],
]) {
  const input = await fs.readFile(path.join(root, "public", inputName));
  const output = await sharp(input)
    .resize(size, size, { fit: "inside", withoutEnlargement: true })
    .webp({ quality, effort: 6 })
    .toBuffer();
  await fs.writeFile(path.join(root, "public", outputName), output);
  report.images.push({
    file: outputName,
    source_bytes: input.length,
    bytes: output.length,
    sha256: hash(output),
  });
}
await fs.writeFile(
  path.join(root, "web-asset-manifest.json"),
  JSON.stringify(report, null, 2) + "\n",
);
console.log(
  JSON.stringify(
    {
      models_before: report.assets.reduce((n, a) => n + a.source_bytes, 0),
      models_after: report.assets.reduce((n, a) => n + a.bytes, 0),
      thumbnail_bytes: report.images
        .filter((a) => a.file.includes("thumb"))
        .reduce((n, a) => n + a.bytes, 0),
    },
    null,
    2,
  ),
);
