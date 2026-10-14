# Garment paint clean-up on the body surface — 2026-10-14

*Type: how-to*

The user saw character-02's coat as "spotty" in game. Measured cause: the outfit atlas is ~10,350
face islands, and the **median coat triangle covers ~3 texels of the 4K map (38% under one texel)**. The
projected paint is one flat chip per triangle, each a little different, with pale/tan smears where the
reference paintings saw the surface at a grazing angle (shoulder tops, flanks). Re-unwrapping does not work
on this mesh: Smart UV Project gives 9,500 islands (the scan has 15k edges sharper than 60 deg and 3.9k
non-manifold edges), and region-segmented conformal/angle-based/minimum-stretch unwraps collapse 16–21% of
faces. Rearranging the existing islands (`scripts/repack_outfit_coherent.py`, kept for atlases with real
texel density) cannot help when a triangle is three texels.

`scripts/clean_garment_paint.py` filters the paint on the mesh instead, in the same UV layout:

1. each face's colour from its own texels (sub-texel faces from their centre);
2. features — faces whose a\*b\* differs from their 2-ring by > 10 (teal stitching, brass, emblem, small
   leather) — are kept exactly;
3. other faces of a class are smoothed over same-class neighbours: area weighted, bilateral in CIELAB with
   lightness counted at 0.25 (smears and chip noise dissolve, hue edges such as shirt/coat stay); a face the
   paintings saw at a grazing angle (|n . view| < 0.25 .. 0.65, views along Y) holds its own colour weakly
   and relaxes its edge test, so trusted head-on neighbours repaint it;
4. texels are rewritten as the new face colour plus the texel's own deviation, scaled by that trust (painted
   detail inside head-on faces survives; smear on grazing faces fades to 15%); gutters refill pull-push.

```powershell
& $B -b --factory-startup <character>.blend --python-exit-code 1 -P scripts/blender/outfit_uv_islands.py -- dump <outfit object> <islands.npz>
python scripts/clean_garment_paint.py --islands <islands.npz> --basecolor <outfit-paint/body_basecolor.png> --mask <outfit-paint/garment_mask.png> --out <fresh dir>
& $B -b --factory-startup --python-exit-code 1 --python scripts/blender/review_outfit_paint.py -- --source <character>.blend --manny-dir <rig-ue5> --paint <old.png> --paint <new.png> --out <review dir> --device GPU
```

Character-02: `work/character-02/coat-clean-20261014/v6/` (speckle between adjacent cloth faces p90
10.8 -> 2.6 CIELAB; 446 feature faces; 20,576 grazing faces). Build `coat-clean-20261014/build-v6/` is the
sleeve-repair release-v2 build with only `outfit-paint/body_basecolor.png` replaced (FBX unchanged,
SHA-256 f4827fb2...). Installed in The Aether Wars with steps `textures texture_policy materials audit`.
Reviews `v1..v6-review/` and `v*-before-after.jpg`.

Retained failures: v1 smoothed the cream shirt into the navy coat (same mask class) and compressed its
lightness to the coat median; v2–v3 kept the shirt but wore down stitching and the back belt/pouch, which
are painted inside larger faces, so per-texel grain must be kept; v4 kept everything including the smears;
v5 faded grazing smears but left the shoulder tops a muddy brown mean; v6 lets trusted faces repaint them.

Limits: no new detail is created — the coat still carries ~150k effective texels of paint. A real AAA coat
needs a retopologised, cleanly unwrapped garment with the paint re-projected at full density. Collar tears,
hair and skin are separate.
