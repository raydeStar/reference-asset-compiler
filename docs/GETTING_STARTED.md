# Getting started

This walks you from a fresh clone to a playable UE5 gallery. Nothing here is
hidden behind chat history: every command is one you can run again.

## You will need

Be honest with yourself about this list before you start. The pipeline is
split so that the expensive parts are optional, but the parts you skip are
the parts that produce new characters.

| Need | For what | Notes |
|---|---|---|
| **Windows 10/11** | everything | The drivers are PowerShell and the AI stages were only verified on Windows. |
| **Python 3.11 or 3.12** | ledger, gates, packaging | `py -3.12` on the PATH. `pip install -e ".[dev]"` pulls numpy, Pillow, scipy. |
| **Blender 5.2 LTS** | retopology, UVs, rigging, deformation tests, renders | Free. Found automatically in Steam or Program Files; else set `RAC_BLENDER`. |
| **Unreal Engine 5.8** | import verification, gallery, cook | Free (Epic launcher). Needs the Third Person template that ships with it. |
| **Disk** | see the tiers below | About 5 GB for the no-AI route, about 60 GB with the AI stages. Measured, not guessed: one character workspace is 0.4 GB, six assets came to 5.7 GB, the UE project 1.5 GB (mostly logs you can delete). |
| **NVIDIA GPU, 24 GB VRAM** | AI geometry and AI texturing only | Verified on an RTX 4090. Texturing refuses to start under 21 GB free. |
| **Hunyuan3D 2.1 checkout + weights** | AI texturing | A separate studio tree named by `RAC_LEGACY_ROOT`; about 15 GB of weights. Layout and steps in `docs/AI_STAGES_SETUP.md`. |
| **ComfyUI + Hunyuan3D wrapper nodes** | AI geometry | The preserved graph is `workflows/geometry/comfyui/hy3d_final_cut.json`; see `docs/AI_STAGES_SETUP.md`. |
| **Auto-Rig Pro** (optional, paid) | better humanoid binding | Not required. `run_rig_candidate.ps1` uses it when present and falls back to the free landmark rig otherwise; see *Rigging with or without Auto-Rig Pro*. |
| **Time** | | A clone to a walkable gallery of your own prop: about an hour. A new character from an image: a working day, most of it review. |

Nothing in this repository redistributes model weights, licensed add-ons,
Unreal Engine, or the reference artwork the cat was built from.

### Disk, in tiers

| Tier | What it enables | Approximate size |
|---|---|---|
| Base | ledger, gates, prop and pre-rigged character compiles, UE gallery | 1 GB Blender + the UE 5.8 install you already have + 2 GB UE project + 0.5 GB per asset |
| AI texturing | Hunyuan3D-Paint 2.1 on your meshes | + 15 GB weights, 2 GB upstream checkout, about 8 GB Python environment with PyTorch |
| AI geometry | Hunyuan3D shape generation through ComfyUI | + ComfyUI itself and the Hunyuan3D shape model, roughly 10 GB |

You do not need a general ComfyUI model library; the pipeline uses one graph
and one model family. `work/ue5-validate/Saved` and `Intermediate` are engine
scratch and safe to delete between sessions.

### Flexibility

- **Tool locations** are discovered, then overridable with `RAC_BLENDER`,
  `RAC_UNREAL_CMD`, `RAC_UNREAL_EDITOR`, and `RAC_LEGACY_ROOT`.
- **Unreal version**: verified on 5.8. `setup_ue5_project.ps1` reads your
  install's `Build.version` and writes the matching engine association, with a
  warning if it is not 5.8; the editor Python calls it relies on exist from
  5.1 onward, the IK Retargeter batch API from 5.8.
- **Blender version**: verified on 5.2 LTS; the stages use `bpy` APIs that
  have been stable since 4.x.
- **Operating system**: the drivers are PowerShell and were verified on
  Windows. Every Blender stage is plain Python run with `blender -b --python`,
  so it is portable in principle; the UE stages need a platform Unreal supports.
- **Rigging**: Auto-Rig Pro if you have it, the free landmark rig if you do not.
- **GPU**: only the two AI stages need one. Everything else runs on CPU.

## 1. Clone and verify

```powershell
git clone https://github.com/raydeStar/reference-asset-compiler.git
cd reference-asset-compiler
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
python scripts\rac_env.py --all
.\scripts\workflow_doctor.ps1
.\scripts\verify.ps1
```

`rac_env.py --all` prints where Blender and Unreal were found. If a line says
`not set`, point at the executable:

```powershell
$env:RAC_BLENDER        = "C:\path\to\blender.exe"
$env:RAC_UNREAL_CMD     = "C:\path\to\UnrealEditor-Cmd.exe"
$env:RAC_UNREAL_EDITOR  = "C:\path\to\UnrealEditor.exe"
```

`workflow_doctor.ps1` is read-only and reports every route. On a machine
without the AI stages it will list them as `[MISSING]` and exit non-zero; that
is information, not a failure of the compiler. `verify.ps1` runs 69 contract
tests and must end with `RAC_VERIFY_OK`.

## 2. Create the UE5 validation project

```powershell
.\scripts\setup_ue5_project.ps1
```

This writes `work\ue5-validate\RacValidate.uproject`, its config, and copies
the Third Person Blueprint character, the Mannequin content and the Input pack
from your own engine install. It never deletes anything and refuses to touch an
existing project without `-Force`.

## 3. Compile a prop you already have (no AI, no GPU)

Copy `recipes/office-chair-ai-v2.json` to `recipes/my-crate.json` and point it
at any mesh and base-color texture on your disk. Then:

```powershell
python scripts\compile_prop.py recipes\my-crate.json
python scripts\build_production.py my-crate
python scripts\promote_production.py my-crate
```

You now have `out\my-crate-production\` with an FBX, PNG maps, and a
`.ue5import.json` manifest. `docs/PROPS.md` explains each step.

## 4. Compile a rigged character you already have

Write a recipe with `"kind": "humanoid"` or `"mascot"`, a `skeleton_profile`
from `profiles/skeletons/`, and `material_textures` with a `BaseColor` and a
packed `ORM` (R occlusion, G roughness, B metallic). Use
`recipes/orange-adventurer-cat-ai-v2-production.json` as the template. Then:

```powershell
.\scripts\compile_asset.ps1 -Recipe recipes\my-character.json
```

The skeleton must match the profile exactly: bone names, parents, count, and
at most four influences per vertex. A mismatch is a hard failure with the bone
named, not a warning.

## 5. Import, build the gallery, walk it

```powershell
$env:RAC_ROOT = (Get-Location).Path
$ue = python scripts\rac_env.py --unreal-cmd
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\import_and_verify.py" -unattended -nop4 -nosplash -stdout
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\build_gallery_level.py" -unattended -nop4 -nosplash -stdout
& $ue .\work\ue5-validate\RacValidate.uproject -ExecutePythonScript="$env:RAC_ROOT\scripts\ue5\setup_gallery_playable.py" -unattended -nop4 -nosplash -stdout
& (python scripts\rac_env.py --unreal-editor) .\work\ue5-validate\RacValidate.uproject -game -windowed -ResX=1920 -ResY=1080 -NoTextureStreaming
```

Each headless run takes one to three minutes; the first compiles shaders and
takes longer. `work\ue5-verify.json` lists what the engine actually built per
asset. `work\ue5-gallery-idle.json` lists, per character, which retarget
variant was chosen and how far its pose sits from Manny's. Then record the
import in the ledger:

```powershell
python scripts\record_ue5_import.py my-character
```

## 6. Make a new character from an image

This is the route in the README diagram and in `docs/WORKFLOW_PLAYBOOK.md`.
It needs the AI stages; `docs/AI_STAGES_SETUP.md` says exactly what to install
and where. The short version:

1. `rac new <id> <image.png> --kind mascot --articulation required --skeleton-profile mascot_biped_tail`
2. Generate one geometry candidate; review four clay views; `rac promote modeling_approval`.
3. Cleanup and retopology scripts; review matcaps and wireframes; `rac promote production_retopology`.
4. `run_texture_uv_prep.ps1`, then `run_hy3d21_texture.ps1`; review **calibrated** lit views and unlit albedo; fix landmarks with `project_ai_reference_region.py` or channels with `clamp_region_roughness.py` if needed; `package_character_texture.py`; `rac promote texture_approval`.
5. `run_rig_candidate.ps1` (Auto-Rig Pro or the free landmark rig, then `gate_rig.py` and `deform_test.py`), then `record_rig_and_skin.py` and `record_deformation.py`.
6. Write the production recipe, `compile_asset.ps1`, and step 5 above.

`docs/HANDOFF.md` is the worked example: every command the cat went through,
every rejection, and why.

## Rigging with or without Auto-Rig Pro

```powershell
.\scripts\run_rig_candidate.ps1 -InputMesh <approved_mesh.fbx> -Profile ue5_manny -OutputDirectory <new dir>
```

The command probes Blender for Auto-Rig Pro. With it operational and a
`-HandLandmarks` file, the Auto-Rig Pro candidate runs; without it, the free
landmark route derives the joints from the mesh and Manny's proportions,
builds the skeleton, binds, exports FBX and runs the two gates. Mascots
(`-Profile mascot_biped_tail`) always take the landmark route and need
`-RingProfile` and `-BindingReport` from the retopology and texture stages.
`rig-route.json` in the output says which route ran and why; the `landmarks/`
folder holds overlay renders to review before you trust the bones. Expect the
free route's heat weights to need touch-up on layered clothing, where it falls
back to envelope weights; that is the quality Auto-Rig Pro buys you.

## Where things live

```text
work/<asset>/state.json            the ledger: which stage passed, on what, by whom
work/<asset>/**/*.json             receipts with hashes for every attempt
docs/evidence/<asset>-*.json       compact evidence checked into Git
out/<asset>/                       compiled package + .ue5import.json
work/ue5-validate/                 the disposable UE project
docs/DECISIONS.md                  what failed and why, so you do not repeat it
```

## When something fails

- **A gate fails.** Read the JSON it wrote; the failure names the bone, the
  texel count, or the deviation. Fix the input and rerun; attempt directories
  refuse to be overwritten, so use a new attempt name.
- **The AI paint crashed on teardown** (`-1073741819`). Its outputs were written
  before the crash and validated; do not rerun it, record it.
- **Characters look washed out in a Blender render.** Use the `calibrated`
  argument to `render_turnaround.py`. See `docs/DECISIONS.md`.
- **Characters are invisible in the UE gallery.** Check
  `work/ue5-gallery-idle.json` for `ok: false`; the retargeter needs the root
  scale compensation the setup script applies.
- **Hands twist under the retargeted idle.** Chain alignment cannot fix roll.
  Open the retargeter under `/Game/Compiled/Retargeted/<run>/Rigs/` and rotate
  `hand_l` / `hand_r` in the target retarget pose.
