# Crate: the runnable static-prop example

A public-domain (CC0 1.0) unit cube with normals and UVs, a 64x64 base-color
PNG, and the recipe that compiles them. It exists so a fresh clone can exercise
the static-prop route without the workstation-bound `work/` tree the checked-in
`recipes/*.json` point at. It is a compile-mechanics example, not an
image-conditioned asset; nothing about it passes an artistic gate.

## Files

| File | What it is |
|---|---|
| `crate.obj`, `crate.mtl` | 8 vertices, 6 quads, one material `MAT-Crate`, six non-overlapping UV islands, 1 m tall with its base on Z=0 |
| `crate_basecolor.png` | 64x64 neutral wood base color, identical across faces |
| `crate.json` | the `static_prop` recipe; the same shape as `recipes/office-chair-ai-v2.json` |
| `make_crate_assets.py` | regenerates the three files byte-for-byte; standard library only |

## Run it

From the repository root, with Blender installed (found automatically or via
`$env:RAC_BLENDER`):

```powershell
python scripts\compile_prop.py examples\crate\crate.json     # join, scale to 0.6 m, rename material
python scripts\build_production.py example-crate --no-sweep --strategy passthrough --resolution 256 --samples 4 --skip-render
python scripts\promote_production.py example-crate            # publish out\example-crate-production\
```

`compile_prop.py` writes an isolated attempt under
`work/example-crate/compile-attempts/<run-id>/` and publishes
`out/example-crate/` only when the normalization report, FBX and texture hashes
all check out. It refuses to run if `out/example-crate/` already exists; delete
that directory only if it is disposable, or change `asset_id` to retain it. Recipe paths are resolved
against the current working directory, which is why the commands start at the
repository root.

`compile_prop.py` accepts FBX, GLB/glTF or OBJ as `source.authority_fbx`
(`scripts/blender/normalize_prop.py`, `import_authority`). Textures other than
PNG are re-encoded to PNG when staged.

## What this does not prove

The example was compiled, baked and published locally with Blender 5.2.1 on
2026-09-11, using the bounded CPU commands above under a fresh test asset id.
CI checks deterministic fixture regeneration; it does not install Blender.
The texture gate checks the atlas against `profiles/skeletons/static_prop.json`.
This deliberately plain fixture tests packaging, scale and gates, not texture
detail, image reconstruction, visual quality, or cooked runtime. The first
fixture used different colors per face and failed the baked-light correlation
check; that failed test attempt was retained, and the neutral fixture passed
without weakening the gate. To
compile your own prop, copy `crate.json` to `recipes/<id>.json`, point
`authority_fbx` and `BaseColor` at your files, and write a measured
`target_height_reason`.

`build_production.py` refuses an existing attempt directory. Choose a new
`--production-name prod-v3` for another bake and pass the same option to
`promote_production.py`. A published `out/<asset>-production` is also immutable;
use a new asset id for another published derivative. A fixture without a ledger
does not gain any approval from these mechanical checks.

## License

`crate.obj`, `crate.mtl`, `crate_basecolor.png` and `make_crate_assets.py` are
dedicated to the public domain under CC0 1.0. The rest of the repository is MIT.
