# Production readiness, end to end

Run 2026-08-31 against UE 5.8.2. Every claim below is a measurement, and the
script that produced it is named.

## The chain

| Stage | Tool | Result |
|---|---|---|
| Build | `scripts/build_production.py` | 4 characters pass retopology, texture, rig and deformation gates; 1 static prop passes retopology and texture |
| Publish | `scripts/promote_production.py` | `out/<asset>-production/`, authorities untouched |
| Import | `scripts/ue5/import_and_verify.py` | 10 packages, 0 failed checks, textures confirmed sampled |
| Skeleton | `scripts/ue5/verify_manny_compatibility.py` | compared against Epic's `SKM_Manny_Simple` |
| Animation | `scripts/ue5/verify_animation.py` | Manny animation drives every bone |
| Collision + LOD | `scripts/ue5/build_physics_and_lods.py` | PhysicsAsset on all four, LODs measured |
| Level | `scripts/ue5/build_gallery_level.py` | 8 characters and 4 prop placements, feet and casters on Z=0 |
| Cook | `-run=Cook` | 546 packages, **0 errors, 0 warnings** |
| Package | `RunUAT BuildCookRun` | **BUILD SUCCESSFUL**, 909 MB, 40 production files staged |
| Run | packaged `RacValidate.exe` | map loads, **0 errors, 0 warnings** -- and see below: that is not the same as looking right |

## The cooked build was shipping grey characters

A frame captured from inside the packaged build -- not from the editor, and not
from its log -- showed all four characters flat grey with correct geometry and
correct normals, while the office chair beside them was fully textured.

`M_RAC_CharacterMaster` had `used_with_skeletal_mesh` set to False.

A material compiles one shader permutation per vertex factory it declares it is
used with, and skeletal meshes are not in that list by default. In the editor
this is invisible, because `automatically_set_usage_in_editor` is on: the first
time a skeletal mesh draws with the material the flag is set and the shader is
compiled on the spot. A cooked build has no shader compiler. The permutation was
never cooked, the material fell back to the engine default, and every character
rendered grey. The chair looked correct in the same build only because it is a
StaticMesh, whose usage is on by default -- which is how the fault surfaced at
all: two asset kinds in one frame, one of them right.

None of the existing checks could see it. The cook reported 0 errors and 0
warnings, because it is not an error. The import verification passes, because
the material IS assigned and DOES sample the right textures -- in the editor.
The rig, texture and deformation gates all run before the engine is involved.

`ensure_master_material` now sets `used_with_skeletal_mesh`,
`used_with_morph_targets` and `used_with_static_lighting` before compiling,
repairs a master that was built without them, and reads the flags back --
setting a property that does not take is silent, and the symptom does not
appear until something is cooked and run.

**The lesson is the check, not the flag.** A packaged build has to be looked at,
in a frame, from inside itself. `work/ue5-evidence/packaged-build-in-game.png`
is that frame and should be recaptured whenever the material graph changes.

## Static props, 2026-08-31

`office-chair` is the first asset compiled that has no skeleton, and it is the
repeatability control `HANDOFF.md` asks for. The route, what differs from the
character path and why, and what is not done are all in `docs/PROPS.md`.

| | |
|---|---|
| Source | 38 objects, 5,464 tris, 6 materials, 2.460 m |
| Compiled | 1 mesh, 5,336 tris, 1 material, 1.019 m |
| Scale basis | seat top lands on field-scout-male's knee (0.489 m), and the base measures 0.67 m across, which is a real office chair base |
| Gates | texture PASS at 2048 / 103 texels/cm2 / 183 islands; rig and deformation skipped by kind and recorded as skipped |
| UE 5.8.2 | StaticMesh, 101.9 cm, 3 LODs, collision generated, 0 failed checks |

## Close-up review, 2026-08-31

A reviewer at close range in `L_RacGallery` found three things the gates did
not. Two were geometry defects the compiler could see once it was told how to
look, and are fixed; one is a texture defect in the accepted authority and is
recorded rather than repainted. Full evidence in
`docs/DEFECTS-CLOSEUP-REVIEW.md`.

| Reported | What it was | Status |
|---|---|---|
| Something sticking out of the man's face | His eyeballs are modelled 6 cm in front of his face; from three-quarters the far one hangs in open air beside his cheek | **Fixed** -- set back a measured 46.5 mm |
| The stamp is over the girl's hair | Her `_Face` material is a frontal projection that covers the fringe and ends in a straight horizontal cut across the hair | **Not fixed** -- inherited from the authority, and repairing it is a texture pass, not a compiler job |
| The fox has missing holes around his eyes | 181 boundary edges survive the heal, in a crescent around each socket; you see into his head through them | **Fixed** -- eye plates held out of the remesh, then boundary loops capped: 0 boundary edges |

Re-verified after the repairs: 8 packages import into UE 5.8.2 with **0 failed
checks**, heights 199.6-200.0 cm (ninja-man 180.0), 3 LODs each, and the review
map rebuilt with 8 characters, one copy of each.

## Animation, measured

Bones the sequence actually drives on each character. Tracks for bones a
character does not have are skipped by the engine and are not failures.

| Character | MM_Idle | MF_Unarmed_Jog_Fwd |
|---|---|---|
| field-scout-female-production | 87/87 driven, 59 moving | 87/87, 60 moving |
| field-scout-male-production | 87/87 driven, 59 moving | 87/87, 60 moving |
| ninja-man-production | 76/76 driven, 56 moving | 76/76, 57 moving |
| fox-mascot-production | 23/27, 20 moving | 23/27, 21 moving |

Every sampled pose is finite. The fox's four undriven bones are `tail_01..03`
and its custom root, which its manifest already says have no Manny counterpart.

## Collision and LODs

Every character now has a PhysicsAsset, created with
`SkeletalMeshEditorSubsystem.create_physics_asset` and reported compatible.
None had one before, which meant none could be hit, ragdoll, or appear to a
physics query.

`unreal.PhysicsAssetFactory` is not the route: its only members are
`create_new` and `script_factory_create_file`, and driving it from Python
returns nothing.

LOD reduction was the open question, because auto-reduction is unreliable on
meshes made of many disconnected shells -- which field-scout-male and ninja-man
are. It holds up:

| Character | LOD0 | LOD1 | LOD2 |
|---|---|---|---|
| field-scout-female | 46,796 | 16,060 (34%) | 8,560 (18%) |
| field-scout-male | 37,410 | 13,104 (35%) | 8,090 (22%) |
| fox-mascot | 46,026 | 15,965 (35%) | 8,426 (18%) |
| ninja-man | 45,685 | 14,491 (32%) | 8,017 (18%) |

## One master material, four instances

`M_RAC_CharacterMaster` with `BaseColor`, `ORM` and `Normal` texture
parameters and a `HasORM` scalar. Each character is a
`MaterialInstanceConstant` of it, so there is one graph and one shader instead
of eight.

This took three attempts and the first two shipped white characters. Both
failures were the same thing and neither announced itself:

**A Masks sampler needs a Masks default texture.** Giving the ORM parameter
`/Engine/EngineMaterials/DefaultDiffuse` -- an sRGB texture -- is a compile
error. The material then silently falls back to the engine default at runtime,
which is a white character. Nothing in the import said so; the cook reported
"0 errors, 2 warnings" and the warnings were exactly this. No engine texture
is imported as `TC_Masks`, so the default is taken from the cohort's own ORM
maps, where it is never seen because every instance overrides it.

**And `Normal` needs no such guard**, because a flat normal map and no normal
map are the same surface -- but `ORM` does, since there is no stock texture
meaning "no occlusion, cloth roughness, not metal". The channels are blended
against explicit constants through `HasORM`, which each instance sets.

Two gates were added so this class of failure cannot ship again:

- `materials_textured` reads what each material actually samples and requires
  the manifest's textures to be among them. `materials_assigned` only ever
  asked whether *a* material was assigned, which is how "not
  WorldGridMaterial" got mistaken for "textured".
- The master material is checked for a non-zero pixel-shader instruction count
  immediately after it is built, rather than discovered in a cook warning.

`get_used_textures` answers for a `Material` and returns nothing for a material
INSTANCE, which reads identically to "this material has no textures" -- so the
check asks instances for their parameter values instead.
