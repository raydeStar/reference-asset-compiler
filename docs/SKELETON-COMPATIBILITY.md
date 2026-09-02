# Skeleton compatibility, measured against Epic's Manny

Run 2026-08-31 by `scripts/ue5/verify_manny_compatibility.py`, headless in
UE 5.8.2 against `/Game/Mannequins/Meshes/SKM_Manny_Simple` as Epic ships it.

Until now "direct compatibility with the UE5 Manny animation ecosystem" was
checked against a hand-written profile in this repo, which is worth exactly as
much as whoever typed it. Epic's animations are bound to Manny's skeleton, so
that is the thing to match.

Manny has **89 bones**.

| Asset | Bones | Missing from Manny | Verdict |
|---|---|---|---|
| field-scout-female-production | 87 | `center_of_mass`, `interaction` | Manny animation plays |
| field-scout-male-production | 87 | `center_of_mass`, `interaction` | Manny animation plays |
| ninja-man-production | 76 | 13, incl. `spine_04`, `spine_05`, `neck_02`, second twists | UE4 Mannequin; needs an IK Retargeter |
| fox-mascot-production | 27 | 66 (it is a fox) | Custom rig, retarget by chain |

The two bones the humanoids lack are Epic's utility bones: `center_of_mass` is
a physics helper and `interaction` is an attachment point. Neither is skinned
and neither is driven by the animation assets, so their absence does not stop
Manny animation from playing. Everything Manny actually animates is present,
including every twist bone and the full finger hierarchy.

**The manifests were already telling the truth.** ninja-man declares
`ue4_mannequin` and says an IK Retargeter is required; fox-mascot declares
`mascot_biped_tail` and says its tail has no Manny counterpart. This run is
independent evidence for claims that were previously only asserted.

## How it had to be done

Two obvious routes do not work headless in 5.8, and both fail in ways that
look like something else:

- `unreal.Skeleton` exposes no bone accessor to Python. The import verifier
  already works around this by reading asset-registry tags, which give a count
  and no names.
- Exporting a skeletal mesh to FBX returns False from
  `Exporter.run_asset_export_task` under every combination of exporter and
  options, without raising.

A `SkeletalMeshComponent` spawned into the transient editor world does expose
`get_num_bones` and `get_bone_name`, so the meshes are read there.

One trap worth recording: `SK_Mannequin` is the **Skeleton** asset, not the
mesh. Loading it and assigning it to a component fails inside a property
conversion and surfaces as `TypeError: NativizeObject: Cannot nativize
'Skeleton' as 'Object'`, which reads like a Python problem rather than "you
picked the wrong asset". The mesh is `SKM_Manny_Simple`.
