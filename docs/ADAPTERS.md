# Adapter policy

The adapter registry describes capabilities, not quality rankings. Each adapter
is externally installed and configured; the compiler does not redistribute
weights or licensed software.

## Geometry and texture candidates

- **Pixal3D**: high-resolution geometry and PBR candidate.
- **TRELLIS.2**: geometry/PBR candidate and existing-mesh texture challenger.
- **Hunyuan3D 2.1**: geometry/PBR candidate and existing-mesh texture
  challenger.

All three remain isolated candidates until they win fixed-view modeling or
texture approval. Front-view appeal alone is insufficient.

## Articulation candidates

- **AniGen**: mesh, skeleton, and skinning challenger. It must prove complete
  chains and deformation quality before replacing a production backbone.
- **Auto-Rig Pro**: licensed, user-supplied Blender humanoid backbone. It is not
  bundled and must pass UE skeleton, bind, influence, and deformation gates.
- **Blender custom rig**: explicit-profile path for mascots and other supported
  articulated assets.

## Local adapter configuration

Machine paths, credentials, model locations, and command templates belong in
ignored `config.local.json`, never in the portable registry. A future execution
adapter should record:

- exact upstream commit or model revision;
- command and environment;
- source hash and seed;
- runtime and peak VRAM;
- output hashes;
- terminal status and log path.

Do not auto-retry a crashed inference. Do not kill user GPU processes to obtain
VRAM. Wait or report the resource blocker.
