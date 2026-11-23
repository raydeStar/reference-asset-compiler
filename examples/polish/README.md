# Surface finishing recipes

These examples bind retained local Raider and Remora inputs. The
[canonical character surface workflow](../../docs/CHARACTER_SURFACE_WORKFLOW.md)
explains the diagnosis, reference and review decisions around these commands. Large character binaries and
generated references are not distributed in the repository. Do not substitute a
different file and keep its old hash; create a new recipe with honest provenance.

From the checkout, with `python -m pip install -e ".[polish]"`:

```powershell
$env:RAC_BLENDER = 'C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe'
rac polish examples/polish/raider-collar.json --output work/raider-polish-20261105/my-collar-replay01
rac polish examples/polish/raider-cuff-repack.json --output work/raider-polish-20261105/my-cuff-replay01
rac polish examples/polish/raider-ears.json --output work/raider-polish-20261105/my-ear-replay01
rac polish examples/polish/remora-tunic-ghosts.json --output work/remora-airship-20261106/my-tunic-replay01
```

- **raider-collar.json:** restore 12 acquired faces, capture guides, map the saved
  concept-conditioned torso reference, prune, repair bounds and inspect. It also
  renders eleven views and packs/reopens a review `.blend`. Final model SHA-256:
  `5136a551e09b2f94a498895b22b9c7fb5cd576767e80dc7640857539d8dea36f`.
- **raider-cuff-repack.json:** exercise general UV/map transport on an earlier
  acquired cuff primitive. This is a transport review, not the final Raider
  delivery and not a new AI repaint. It intentionally retains the original maps.
- **raider-ears.json:** project retained, clay-conditioned AI side references
  into both scoped ear regions, prune, repair bounds, inspect and render thirteen
  fixed/closeup/light views. Source is a retained derivative of Candidate05 with
  bounded acquired ear-interior fairing; the recipe does not infer or regenerate
  that anatomy decision. Prompts, inputs and rejected references are retained in
  `work/raider-polish-20261105/ear-alignment-20261106/`.

- **remora-tunic-ghosts.json:** remove painted remnants exposed after old hair
  geometry was removed. Capture the exact body material, project the retained
  concept-conditioned cloth reference into a bounded region, soften obsolete
  relief there, prune and render fixed/closeup/light views. Face, eyes, hair and
  geometry remain protected. Generation prompt and inputs are under
  `work/remora-airship-20261106/tunic68/references/`; rejected scope is `tunic69`.
- **remora-braided-knot.json:** the separate acquired-hair replay recipe, run with
  `python scripts/replay_acquired_hair.py examples/polish/remora-braided-knot.json --out <new-directory> --blender <blender.exe>`.
  It is not a `rac polish` recipe and does not regenerate or assemble the entire
  character. Remora's asset-specific face/collar replay remains separately retained
  at `work/remora-airship-20261106/replay65/replay.py`.

Use fresh attempt directories. Resume a completed/waiting run with the same
recipe and `--resume`. To start another asset rather than replay these inputs,
use `rac polish-init`; see the [workflow guide](../../docs/POLISH_WORKFLOW.md).
