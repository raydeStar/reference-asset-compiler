# IntrinsicAnything: isolated albedo challenger

**Current verdict (2026-09-05): rejected for the Sunset character's multiview
lighting transfer.** Exact sides collapsed to black, an oblique orbit still
lost one side, and vertical patches introduced bands/black leg regions.
No Ayric atlas was changed. Stop this route pending a causal defect diagnosis
or a materially different method; see `docs/ESCALATE-sunset-lighting.md`.

This is an experiment, not the default Hunyuan PBR pipeline and not a face
replacement tool. The official single-view model estimates albedo from RGBA
object views. It does not change geometry, UVs, rigs or UE assets. Its base
diffusion resolution is 256 pixels even when the output PNG is 1024 pixels.
The base Ayric probe softened facial landmarks and armor lines; do not copy
that output directly into the approved atlas.

## Pinned sources

- [Official source](https://github.com/zju3dv/IntrinsicAnything), commit
  `e1287870d88fd51d310b8fcd2250057dad8d320e`.
- [Model](https://huggingface.co/LittleFrog/IntrinsicAnything), revision
  `f2f095e1a9a60a45272299127b372488dca4a619`; model card Apache-2.0.
- CLIP source `d05afc436d78f1c48dc0dbf8e5980a9d471f35f6`.
- Taming source `3ba01b241669f5ade541ce990f7650a3b8f65318`.

Keep Python 3.10 separate from the compiler (Python >=3.11). The checked-in
requirements pin the upstream inference core and a compatible NumPy/hub stack;
web/demo/training dependencies not required by inference are omitted. The
execution receipt records every installed version.

```powershell
uv venv --python 3.10 work/toolchains/intrinsicanything-env
uv pip install --python work/toolchains/intrinsicanything-env/Scripts/python.exe --index-strategy unsafe-best-match -r workflows/texture/intrinsicanything/requirements-inference.txt
```

Clone the two pinned source trees into `work/toolchains/IntrinsicAnything` and
`work/toolchains/taming-transformers`. The latter is deliberately imported
from source: upstream uses namespace directories, but its `find_packages()`
wheel contained no importable `taming` module on this machine. The wrapper
verifies revision and source cleanliness; untracked bytecode caches alone
are allowed. Do not patch the neural model to bypass an import failure.

Download the albedo checkpoint/config into
`work/toolchains/intrinsicanything-weights/albedo`, and official CLIP ViT-L/14
into `work/toolchains/intrinsicanything-clip`. The wrapper asserts their exact
hashes before loading. It only redirects CLIP's cache path; inference source
is unmodified. Kornia also loaded a 5,345,580-byte HardNet checkpoint on import.

## Measured sizes on this workstation

These are logical file bytes measured on 2026-09-05, not estimated download
sizes or filesystem allocated space. uv hardlinks and caches affect actual
space usage. The interpreter, uv download/build cache and generated evidence
are additional.

| Item | Bytes |
|---|---:|
| Albedo checkpoint alone | 15,458,840,153 |
| CLIP ViT-L/14 checkpoint | 932,768,134 |
| HardNet import dependency checkpoint | 5,345,580 |
| Isolated environment | 5,446,629,235 |
| IntrinsicAnything checkout including Git | 51,379,710 |
| Taming checkout including Git | 585,195,850 |

The complete measured directories plus HardNet totaled 22,480,161,554 bytes,
including model configuration/cache metadata. Specular model not downloaded.
Do not present 15.46 GB as the complete installation requirement.

## One retained attempt

First generate new RGBA inputs from the unchanged packaged FBX with
`scripts/blender/render_intrinsic_inputs.py`. It uses emission only, Standard
sRGB at exposure0; the calibrated beauty exposure of -1.5 is not input albedo.
Inspect GPU ownership and queue before inference. The probe requires 21 GiB
free conservatively; the observed base run allocated a peak 5,441,026,560 bytes,
which is not a proven minimum for other settings.

```powershell
& work/toolchains/intrinsicanything-env/Scripts/python.exe scripts/run_intrinsicanything_probe.py --upstream work/toolchains/IntrinsicAnything --weights work/toolchains/intrinsicanything-weights/albedo --clip-cache work/toolchains/intrinsicanything-clip --taming work/toolchains/taming-transformers --inputs work/sunset-ayric-v2/texture/intrinsic-inputs-v001 --output work/sunset-ayric-v2/texture/NEW-ATTEMPT
```

The optional `--guidance-receipt <completed-base-attempt/execution.json>` uses
the official high-resolution recipe: 200 DDIM steps, guidance3, 2x2 splits,
one overlap, batch1. It validates same-input lineage and guidance hashes.
Every output directory must be new. Failures are retained and never retried
automatically. View all outputs before any bounded UV transport; a successful
run does not approve the face or waive the independent texture gate.
