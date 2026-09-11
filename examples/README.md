# Examples

Two kinds of file live here.

## `rac plan` intake samples

`humanoid.json`, `mascot.json` and `static-prop.json` are intake manifests in
the shape `rac new` writes to `work/<asset>/intake.json`. They exist for the
CLI smoke test and for reading the routing logic:

```powershell
rac plan examples\mascot.json
```

Their `source.sha256` values are zeros on purpose; they route, they do not
compile. `scene-atmosphere.json` is a `scripts/scene_tools.py` atmosphere
recipe for the workshop level (`docs/SCENE_TOOLS.md`).

## `crate/`: the compile example

`crate/` is a complete static-prop compile that runs from a fresh clone: a CC0
generated cube, a 64x64 base color, and `crate/crate.json`. Start with
[crate/README.md](crate/README.md). The checked-in `recipes/*.json` are the
real assets and point at workstation-bound `work/` or `${RAC_LEGACY_ROOT}`
paths; use the crate to learn the shape, then write your own recipe.
