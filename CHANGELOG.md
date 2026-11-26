# Changelog

Release notes live under `docs/releases/`; GitHub releases carry the same text
and any attached wheel.

## Unreleased

`paint-sections` keeps the card busier and lays sections as they come. The
painter finishes each section's maps (the fills, their conversion and the PNGs)
on a thread while the next section paints, and the pass lays each section over
the first paint as soon as it is written, so little is left once the last one is
painted. The maps are byte for byte the same. The WK-04.1 stair's section pass
took 42 minutes instead of 114, with 26 s left after the last section where
reading and compositing took about 6 minutes; against the stair the owner
passed, the texels that moved lie only on faces no outside view reaches. A
section is about 35 s slower whenever the CPU is busy with other work, such as
another model's bakes or composite, so nothing CPU-heavy should run beside
painting.

`paint-sections` is faster and paints the same. One painter run paints every
section with its models loaded once and writes only the maps; each section's
unseen texels are filled near its own faces instead of across the whole 8192
sheet; and the composite sums and blurs only where a section weighs. On the
WK-04.1 stair a section took 99-132 s instead of 140-197 s, and the composite
4.5 minutes instead of 14.5. The passed stair re-composited from its own
sections is byte-identical; with three sections painted the new way, its
finished maps moved by at most 9/255, on 0.05 % of texels. `--separate-runs`
and `--inpaint-reach 0` bring back the old way.

`project-reference`: the reference picture laid onto the faces of a Pixal3D model
it shows, over the paint. Pixal3D builds its mesh in the picture's camera; the
stage fits that camera (Pixal3D's logged field of view, refined by the outline)
and blends the picture in per texel by facing, line of sight and the cutout, so
the WK-04.3 landing carries its reference's own scratches and dark steel, which
painting in sections had lost. Geometry and picture must be the same image; a
revised picture is refused until the geometry is made again. The Pixal route
bakes occlusion again (the overlapping UVs that broke it are fixed) and, after a
projection, no relief from the paint.

`uv-unwrap` no longer lets two faces share a texel. Smart Project laid the
WK-04.1 stair's folded treads on top of themselves (8.9 % of its texels shared),
which put hidden faces' occlusion and roughness onto visible ones as triangles.
Overlapping faces are now projected again, tighter, until none overlap, and a
layout that still overlaps is refused. The stair's sheet also gained about 55 %
more painted texels.

Pixal3D props look the same in Framewright and Unreal. `bake-detail --no-occlusion`
leaves out the occlusion map, which on Pixal3D's layered game meshes darkened
visible triangles in every viewer that reads it (the stair's treads), and the
browser copy now carries the tangents its normal map was baked against.

Pixal3D meshes the route can use as they come. `level_pair.py` mends each game
mesh: specks, fins on edges shared by three faces, slivers and small holes (the
crate's 9 to 58 open edges went to 0 on four seeds of six). `bake-shape` bakes
again from closer cages where the first bakes a normal facing into the surface,
which removed the stair's black crescent. Notes: [docs/DECISIONS.md](docs/DECISIONS.md).

`pixal-geometry`: one picture to a levelled game mesh and dense mesh with Pixal3D,
in one stage, so Framewright can drive the prop route. `level_pair.py` gains
`--up` (tall and edge-standing pieces), `--flip` and `--height`.

Every GPU stage of the prop route within a 12 GB card, with the same results.
The studio painter at an 8192 sheet peaked at 13.2 to 18 GiB and now at the
diffusion's own 9.1 GiB, maps byte for byte the same (the bake adds one view at
a time; the texel map keeps only covered texels). Pixal3D at 1024 peaked at
14.2 GiB and now at 7.7 GiB, its conditioning exactly the same (NAF upsamples
one attention head at a time). Notes: [docs/DECISIONS.md](docs/DECISIONS.md).

## v0.5.0 — 2026-11-24

Paint by parts. `label-parts` finds a painted model's parts face by face, and in
its reference (Grounding DINO and SAM on 24 renders, votes onto faces, review
views in part colours). `paint-parts` paints each part alone from the reference
with the other parts masked out and lays it on its own faces, so one part's
colour no longer bleeds onto another. `paint-sections` goes over it with its
sections reused. Notes: [docs/releases/v0.5.0.md](docs/releases/v0.5.0.md).

## v0.4.0 — 2026-11-24

Props that hold up at arm's length. A Pixal3D route end to end: Pixal's own
simplification of the same generation as the game mesh (`run_pixal3d.py
--extra-targets`), `level_pair.py`, and a new `bake-shape` stage that bakes the
dense mesh into the normal map. Section paint is baked at texel scale (no more
specks), can be painted on an 8192 sheet, cross-fades between sections, and
keeps the first paint's colour as painted. Notes: [docs/releases/v0.4.0.md](docs/releases/v0.4.0.md).

## v0.3.0 — 2026-11-24

Large models as sharp as small ones. `paint-sections` paints a large model again
in sections at small-prop scale: a 2.2 m skiff went from about 3 mm to about
0.7 mm of surface per painted pixel. It keeps the first paint's colour by default.
`bake-detail --relief-tilt` sets relief from paint to a measured steepness.
New hard-surface finishing stages, an automatic part map, and fixes for the
painter's doubled specular and for seam-cut meshes in the voxel reductions.
Notes: [docs/releases/v0.3.0.md](docs/releases/v0.3.0.md).

## v0.2.1 — 2026-10-31

Faster AI stages: geometry generation is about 3× faster (three views 63 → 21 s,
one picture 55 → 13 s; meshes match to 0.008% of the diagonal), studio paint is
about 40 s faster with byte-identical maps, and the geometry launcher starts
again when run directly under Windows PowerShell 5.1.
Notes: [docs/releases/v0.2.1.md](docs/releases/v0.2.1.md).

## v0.2.0 — 2026-10-30

RAC on a 12 GB GPU: geometry needs 8 GB (byte-identical meshes), studio-route
texture painting peaks under 10 GB at best quality (was 35–44 GB, spilling into
RAM) and runs faster, every AI run records its peak VRAM, and review renders can
use the CPU. Notes: [docs/releases/v0.2.0.md](docs/releases/v0.2.0.md).

## v0.1.2 — 2026-09-11

Stronger lineage and promotion guards, retained compile/bake attempts, consistent
Windows launchers, a shorter resume path and a runnable CC0 crate example.
Notes: [docs/releases/v0.1.2.md](docs/releases/v0.1.2.md).
Completion checklist: [docs/MAINTENANCE_REVIEW_2026-09-11.md](docs/MAINTENANCE_REVIEW_2026-09-11.md).

## v0.1.1 — 2026-09-11

Reliability maintenance for the existing Codex-operated workflow: audits
require every expected stage, failed prop exports stay failed, the installed
CLI works outside the checkout, the doctor gained route profiles, and local
verification matches CI. Notes: [docs/releases/v0.1.1.md](docs/releases/v0.1.1.md);
release: <https://github.com/raydeStar/reference-asset-compiler/releases/tag/v0.1.1>.

## workshop-2026-09-06

The Workshop Update: textures, rigging and the real UE 5.8 showcase (Ayric
v051 in the night workshop, walk GIF, provenance JSON). Release:
<https://github.com/raydeStar/reference-asset-compiler/releases/tag/workshop-2026-09-06>;
the dated record is in `docs/HANDOFF.md` under 2026-09-06.
