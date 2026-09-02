# UE5 validation contract

## Humanoid

The default target is the declared existing UE5 Manny-compatible skeleton. The
importer must not create an unrelated skeleton and call it compatible.

Verify:

- expected root and bone names;
- centimeter scale and sane child-bone translations;
- maximum four skin influences;
- complete finger chains;
- stable bind pose and clean FBX round trip;
- correct materials and texture color spaces;
- representative elbow, wrist, hand, shoulder, neck, waist, knee, and ankle
  poses.

## Mascot and custom articulation

Record a named skeleton profile and verify every required chain. Tail count and
tail chain count are separate contracts; geometry duplication is not accepted
as extra articulation.

## Static objects

Verify scale, pivot, orientation, materials, LOD policy, and collision when the
asset needs physical interaction.

## Runtime acceptance

Capture the asset in the target level with neutral exposure as well as ordinary
game lighting. Run map check. Cook or package the sample. An editor-only render
is useful evidence, but it is not the terminal gate.

## Playable gallery and retargeted idles

`work/ue5-validate` is a disposable UE 5.8 project. To make the gallery
walkable it carries three things copied from the engine install, none of them
redistributed by this repository:

- `Content/Characters/Mannequins/` from `Templates/TemplateResources/High/Characters/Content`;
- `Content/Input/` from `Templates/TemplateResources/High/Input/Content`;
- `Content/ThirdPerson/Blueprints/` from **`Templates/TP_ThirdPersonBP`** (the
  Blueprint template). The C++ template `TP_ThirdPerson` looks identical but its
  Blueprints reference a compiled `TP_ThirdPerson` module and fail to load,
  leaving a spectator pawn.

`Config/DefaultEngine.ini` sets `GlobalDefaultGameMode` to
`BP_ThirdPersonGameMode` and `Config/DefaultInput.ini` uses Enhanced Input.
`scripts/ue5/build_gallery_level.py` places every compiled skeletal and static
mesh with a PlayerStart; `scripts/ue5/setup_gallery_playable.py` builds IK Rigs
from bone names, retargets `MM_Idle` onto every skeleton with limb chains
aligned to Manny and spine/head at reference, compensates the compiled
skeletons' 100x root scale, and writes `work/ue5-gallery-idle.json` with the
pose-mismatch numbers for every variant it tried. Launch with
`UnrealEditor.exe <project> -game -windowed -NoTextureStreaming` to be dropped
in as Manny.

