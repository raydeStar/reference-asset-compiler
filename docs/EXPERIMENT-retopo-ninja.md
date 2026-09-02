# Retopology rejected on ninja-man

Run 2026-08-31. Every attempt to reduce ninja-man's triangle count passes the
automated gates and **fails visual review on the head**. Retopology is rejected
for this character.

He still ships, by the other route: `scripts/build_production.py` keeps his
geometry and his UV layout exactly as authored and does the rest of the stage
anyway -- ambient occlusion, and a weight clamp from eight bone influences to
four, which matters because UE5 truncates to four silently and would otherwise
change his deformation after it was tested. `out/ninja-man/` is untouched;
`out/ninja-man-production/` is the derivative.

## What passes

```
ninja-man: 54,220 -> 28,704 tris (10,166 quads)
rig   ok   (ue5_manny, 4 influences, 0 unweighted)
tex   ok   (49 islands, median 279 px, density ratio 1.67)
deform ok  (5 poses)
deviation from the original: p99 5.7mm, max 28.9mm
```

The body is good. Garments, sash, boots and silhouette all survive, and the
albedo matches the source atlas mean (22.4 against the source's 20.5 -- this
character is genuinely dark, which cost an afternoon of chasing a texture bug
that was not there).

## What fails

The head. Hair reduces to a grey mass, and the face reads as a mosaic of flat
tiles instead of skin, mask and brow. Fixed front views at
`work/ninja-man/prod-v2/closeup/`.

## What was tried, and what it measured

| Attempt | Result |
|---|---|
| Whole-mesh QuadriFlow | Refused: 5 quads in 54,212 faces. He heals into 24 shells and it will not take the lot. |
| Per-shell remesh | Works, and is what the passing build uses. |
| Budget 12,000 -> 20,000 | Head no better; at 20,000 the mask blends into the hair and it is arguably worse. Not a density problem. |
| Budget 30,000 | 62,746 tris, larger than the 54,220 input. Rejected by the no-reduction guard. |
| Preserve "head" shells | Never fires: his head is inside a 21,986-face body shell, not its own shell. Removed, because it also broke field-scout-male. |
| Bake ray 4mm | Head baked black -- rays never reached it. |
| Bake ray 20mm | Reaches, but crosses layers; hard patches sampled off the wrong garment. |
| Bake through a real cage | Bakes field-scout-male entirely black at every offset from 2mm to 27mm. Rejected. |
| Seam angle 50 -> 72 degrees | The one real gain: 5,664 seams and 265 islands (166 under 64 px) down to 3,011 seams and 49 islands, median island 38 px -> 279 px. The face partly returns. Not enough. |

## Why it is worse than the other three

His mesh is a join of 24 shells of layered, ragged cloth. That drives
everything: whole-mesh remeshing is refused, so the budget is rationed per
shell, and his head rides inside a body shell that is cut 4.8x. The head
therefore loses most of its polygons and its share of the sheet at the same
time, and no single knob recovers both.

The other three are not like this. field-scout-female and fox-mascot heal into
meshes QuadriFlow accepts whole, and field-scout-male's body is refused so it
is preserved rather than reduced.

## What would be worth trying next

Not another budget or seam value; both were swept and neither is the binding
constraint.

1. **Remesh the head separately on purpose.** Split the head off the body shell
   by bone region before remeshing, give it its own generous budget, and stitch
   afterwards. The machinery to classify by region already exists.
2. **Find out why QuadriFlow refuses whole meshes here.** field-scout-male's
   body shell is manifold by every measure taken -- 0 boundary edges, 0 edges
   over two faces, 0 bowtie vertices, 0 loose or wire geometry, 0 zero-length
   edges, 0 duplicate faces, consistent winding, positive signed volume, genus
   1 -- and is still refused, while a genus-19 shell from the same character is
   accepted. Something outside that list is the trigger.
3. **Author the head by hand.** He is one character; the pipeline does not have
   to solve every case.


## Postscript: what the failed attempts were worth

Two findings came out of this that changed the pipeline for every character.

**QuadriFlow accepts open meshes.** With `use_preserve_boundary=True` it
remeshed field-scout-male's torso with 5,092 boundary edges. Boundaries were
never what it was refusing, which rules out a whole class of explanation for
the refusals and makes region-by-region remeshing mechanically possible.

**But region pieces cannot be stitched back.** `use_preserve_boundary` keeps
the SHAPE of a cut, not its vertices -- QuadriFlow re-samples along the same
curve with its own spacing. The pieces no longer share points, and the result
is a character torn along every seam. It is real geometry, not a shading
artifact: the holes show in a matcap. Snapping the remeshed boundary onto the
original cut vertices closed 480 of them; welding only the open vertices at
6mm left 5,424 open edges. Per-region remeshing is not usable without a proper
stitch, and is not enabled.

The third finding was the one that let him ship. Re-unwrapping a mesh that was
NOT remeshed is much worse than leaving it alone: the semantic layout is built
for a clean quad field, and on the original triangle soup it took him from 942
islands at 71.3% coverage and 146 texels/cm2 to 1,630 islands at 44.1% coverage
and 76-108 texels/cm2 -- visibly draining the blue out of his clothes. Where
the geometry is kept, the UVs are kept with it.
