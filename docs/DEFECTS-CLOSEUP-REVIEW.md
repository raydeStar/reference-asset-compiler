# Close-up review: three defects, and what each one turned out to be

A reviewer looking at the UE5 gallery at close range reported three things:

1. Something sticking out of the man's face.
2. The stamp is over the girl's hair, and looks funny.
3. The fox has missing holes around his eyes.

All three were real. Two were introduced or amplified by the compiler and are
now fixed; one is inherited from the accepted authority and is not the
compiler's to repair. This is the evidence for each.

Everything below is reproducible from `work/_defect/`.

---

## 1. field-scout-male: the eyeballs were 6 cm in front of his face

**Verdict: real, inherited from the authority, repaired in the derivative.**

Marching a ray forward through his head along the eye axis (x=-0.044,
z=1.784) gives the layering directly:

| Surface | y |
|---|---|
| EyePupil front | -0.1710 |
| EyeSclera back | -0.1503 |
| **head skin, first hit** | **-0.1137** |
| back of skull | +0.1293 |

The entire eye assembly sits 37 mm to 57 mm in **front** of the skin at its own
position. Head on it is invisible: the eyes line up over the sockets and the
texture does the rest, which is why every fixed-view gate passed. At
three-quarters the far eye clears the bridge of his nose and hangs in open air
beside his cheek — a grey capsule with a blue dot on the end.

Present identically in `out/field-scout-male/field-scout-male.fbx`, so the
compiler did not cause it. It is also the same defect as the earlier "his eyes
look like he's bulging a bit" note.

### Why no existing metric saw it

Both surfaces are individually valid — correctly wound, correctly wrapped,
correctly textured. The defect is only where they sit relative to each other.
Deviation, silhouette IoU, UV coverage and bake coverage all measure one
surface at a time.

The first detector written for it was also wrong. A signed distance to the
nearest body face reports **zero** vertices outside, because around an eye
socket the nearest face is often the inside of the eyelid, whose normal points
back at the eyeball. Two further false starts are worth recording:

- Measuring against the largest shell. His head is a separate 3,494-vertex
  shell from his 29,340-vertex torso, and against the torso every ray escapes,
  because it does — the torso is 3 cm below his eyes.
- Requiring the eye to be invisible from off-axis. An eye is *meant* to be
  visible; that is what the lid aperture is for, and a wide aperture leaks rays
  well past 55° off the forward axis.

### The test that works

A vertex is outside the silhouette if, along some axis, rays in **both**
opposing directions escape without hitting the host. Such a point has open air
on both sides: it is beside the head, not framed by it. A point seen through
the lid aperture fails this test correctly — the opposite ray hits the back of
the skull.

Validated against renders across a setback sweep:

| Setback (straight back) | left eye outside | right eye outside | renders as |
|---|---|---|---|
| 0 mm | 624 / 624 | 624 / 624 | capsule clearly detached |
| 48 mm | 331 / 624 | 0 / 624 | one eye still breaking out |
| 56 mm | 6 / 624 | 0 / 624 | faint nub |
| 64 mm | 0 / 624 | 0 / 624 | clean from every angle |

The metric reaches zero exactly where the picture becomes clean.

### The repair

`settle_prop_shells()` in `scripts/blender/retopo_bake.py`, opt-in per asset
via `SETTLE_PROPS` in `scripts/build_production.py`. It measures the smallest
setback at which no vertex of the assembly is outside its host's silhouette and
applies it; nothing is configured by hand.

Measured for field-scout-male: 46.5 mm and 39.5 mm along each eye's own axis.
**46.5 mm is applied to both.** The difference between the two is asymmetry in
his head, not two independent answers, and applying it would leave the face
lopsided.

Scope is narrow on purpose. Only shells whose faces all use materials matching
the token are considered. The geometric description — a small shell sitting
outside the body it belongs to — fits ninja-man's shoulder plates and
fox-mascot's flat eye decals just as well, and both belong exactly where they
are. Sinking them would be the compiler inventing a defect.

### The bug that made the first fix do nothing

The build reported settling both eyes 46.5 mm and shipped them exactly where
they started.

field-scout-male carries five shape keys: a Basis plus four corrective elbow
blendshapes. With shape keys present, `mesh.vertices[].co` is not what the
object shows. The moment anything enters edit mode — and the heal that follows
immediately does, to weld the export's split vertices — Basis is written back
over the mesh and the move is silently undone. The other three characters have
no shape keys, which is why this looked like it worked in isolation.

Every key block now gets the same rigid shift, so the correctives keep the
deltas they were authored with.

**Result:** 67,907 → 67,939 triangles, deviation p99 0.51 mm, silhouette IoU
1.000, bake coverage 100%. The capsule is gone at 0°, 30° and 60°.

---

## 2. field-scout-female: the face projection is stamped across her hair

**Verdict: real, inherited from the accepted authority, NOT repaired.**

There are two separate things on her head, and only one of them is what the
word "stamp" usually means in this project.

### The eye-logo decal is already gone

An eye-shaped logo was painted into her body atlas at (1368, 750). An earlier
pass found it (`work/field-scout-female/decal-report.json`: 2 stamps, 99,050
pixels) and the shipped authority no longer contains it — template-matching the
"before" crop against `T_FieldScoutFemaleBody_BaseColor.png` finds the location
but the graphic itself has been inpainted out.

That region maps to the **back of her head, in her hair**
(`work/_defect/female-marked.png` paints it magenta on the model). So the decal
was on her hair, and its inpaint smudge still is.

### The band across her hair is the face projection running out

The more visible defect is a hard horizontal band across the top of her head,
present at 0°, 40° and 90°, in both the authority and the production build, in
beauty and in unlit albedo alike. It is not geometry — the clay pass shows
ordinary hair cards with no plane through them.

Tinting the **Face** material magenta
(`work/_defect/female-facemark.png`) explains it. `M_FieldScoutFemale_Face` is
a 1024 frontal projection, and it covers not only her face but the fringe of
hair over her brow and part of the hair at her temples. Its coverage ends in a
straight horizontal cut across the hair, and the band in the render sits
exactly on that cut.

So the face image is stamped onto her hair and stops in a straight line. That
is what "the stamp is over the girl's hair" describes.

### Why it is not repaired here

Fixing it means either re-projecting the head texture or reassigning those hair
faces to the body atlas and repainting the difference. Both are texturing work
— Stage 4 — and the compiler explicitly does not repaint textures. Neither is
it a repair the compiler could make safely by guessing: the reference image
never saw the underside of that fringe, so there is no correct answer to
recover, only one to invent.

Recorded, evidenced, and left for a texture pass. The production build does not
make it worse; it reproduces the authority's band at the same place and the same
strength.

---

## 3. fox-mascot: there really were holes around his eyes

**Verdict: real, present in the authority, made larger by the remesh, now
fixed.**

Two separate faults sat on top of each other.

### The eye plates were being remeshed into the head

His eyes are four flat plates stacked 5 mm apart in front of orange fur —
outline, iris, pupil, highlight — and the whole character was going through
QuadriFlow. The remesh absorbs the plates into the head, and the bake then has
to choose, for every texel near an eye, between surfaces a fraction of a
millimetre apart with fur immediately behind them. It chose wrongly in patches:
brown wedges appeared to have been bitten out of his eyes.

`split_off_prop_shells()` now holds those 960 triangles out of the remesh and
joins them back before the unwrap, so the bake ray leaves a plate and arrives
back on the same plate. They are still re-unwrapped with everything else, which
is what repairs their UVs — in the source all four pile 1.67× the sheet on top
of each other.

The first version of this split inverted: face selection flags written in
object mode are discarded when the mesh is handed to the edit-mode bmesh, which
restores whatever was selected last — everything. It separated the whole
character, left QuadriFlow an empty mesh, and the build failed several stages
later with an unrelated-looking message. Selection is now written inside edit
mode, and a size check refuses a split that keeps more than it leaves behind.

### The head genuinely had holes in it

`fill_holes(sides=64)` only closes what it can fan-triangulate, and it gives up
on the rest: the heal left **181 boundary edges**, in a crescent around each eye
socket. The clay pass shows them plainly — you see straight into his head. The
authority has them too, smaller and more ragged; the remesh tidies them into
larger, cleaner crescents.

`make_manifold` is now run on the fox **after** the remesh, opt-in via
`CLOSE_HOLES`. The order is not a preference: running it *before* QuadriFlow was
tried previously and made QuadriFlow refuse his body outright, which is recorded
in that function's own docstring. Afterwards it is safe, and the caps are
created before the unwrap, so they get UVs and bake like any other face.

It is opt-in because capping every boundary loop is not universally right —
field-scout-male's eyelid aperture *is* a boundary loop, and closing it would
seal his eyes inside his head.

**Result:** 0 boundary edges, 0 edges over two faces, 0 bowties. 69,545 →
48,042 triangles, deviation p99 3.4 mm, bake coverage 99.78%. The voids are
gone and the eyes read as clean cartoon eyes at normal viewing distance.

What remains on the fox is the faceting in his ears, which is the known
QuadriFlow-versus-spiky-silhouette compromise, and a lightly stepped cap
between the eyes where the holes used to be — visible only at extreme close
range, and no longer a hole.

---

## Method note

Two of these three were invisible to every gate the compiler runs, and the
third was visible only as a texture the gates had no opinion about. What found
them was fixed-view close-up renders in three passes — beauty, unlit albedo,
and clay — compared side by side between the authority and the production
derivative.

The clay pass is what separated "geometry" from "texture" in every case, and it
is what should be rendered first the next time something looks wrong. A beauty
render alone would have sent the eyeball hunt into the bake code, and the
fox's holes into the texture code, and neither is where the defect was.
