# Finishing a template-conformed head

`scripts/finish_template_head.py` turns a conformed template head (from
`conform_head_template.py`) and its hair shell (from `build_hair_shell.py`)
into a painted, reviewable head in one command. CPU only by default; about 70 s
without renders, about 2 min more for nine 1024 px Cycles renders.

## What it does

1. **One continuous neck** (`close_head_neck.py`). The skull and face keep the
   fit (head-bone weight >= 0.6). Below them, the jaw underside, neck and collar
   take the template's own neck, moved by a harmonic continuation of the face's
   displacement. It is one mesh on the template topology, so there is no
   face/neck seam and every expression unit moves both. The neck ends on a
   collar curve: low at the throat, a U to the sides, rising to the nape.
   This replaces an acquisition neck that is cut or torn, and with it the
   separate continuation/adapter pieces and their expression gaps.
2. **Hair hugging the neck** (`trim_hair_shell.py`). Shell triangles below the
   ears and within 10 mm of the skin are dropped.
3. **Paint** (`paint_head_from_views.py`). Front, side and back pictures as
   before. The crown, which no picture faces, is painted from the back
   picture's strands. Each upward-facing hair point above the ears is rolled
   55° back over the top of the head.
4. **Hair the pictures call skin** (`trim_hair_by_paint.py`). Shell triangles
   below the ears whose paint is nearer the median skin than the median hair
   are dropped. Paint step 3 also clears hair the profile draws over the neck: below the ears, behind their front edge, and darker than 0.8 of the face's skin brightness.
5. **Review renders** (`blender/render_painted_head.py --device CPU`): five
   views and four expressions.

The same inputs give byte-identical meshes and textures (checked with a replay
on 2026-10-06). `manifest.json` in the output records every input and output
hash.

## Open-source status of each piece

| Piece | Licence |
|---|---|
| Scripts (this repo) | the repo's licence |
| Python, NumPy, SciPy, Pillow | open source (PSF, BSD, HPND) |
| Blender (renders, template export) | GPL |
| MakeHuman hm08 template via MPFB | assets CC0, MPFB GPL |
| Face landmarks: `detect_face_landmarks_dwpose.py`, DWPose `dw-ll_ucoco_384` weights run directly with PyTorch | Apache-2.0 weights, BSD PyTorch: open source. The conform and paint scripts read its 68-point layout. |
| InsightFace buffalo_l (`detect_face_landmarks.py`, the earlier route) | non-commercial research licence: **not open source; do not use for the pipeline.** The ComfyUI DWPose wrapper code is OpenPose-licensed (non-commercial), so it is not used either; only the weights are. |
| Head acquisition and the front/side/back guidance pictures | frozen inputs from earlier work; their generators' licences still need confirming |

## Open route, end to end (v10, Ennix, 2026-10-06)

1. `detect_face_landmarks_dwpose.py` runs on the front picture, a front render of the template, and the left profile.
2. `conform_head_template.py` uses `--picture-landmarks`, `--template-landmarks` and `--template-camera` with those JSONs (68-point). It takes 14 s.
3. `finish_template_head.py` uses the same template and profile JSONs. It takes about 70 s without renders.

The likeness matches the InsightFace run: the features hold to the picture within 0.10 mm median, and the eyes shift the same.

## Known gaps (v9/v10, Ennix)

- In profile, the collar dips to a point at the throat, and the nape has one
  notch where a hair flap meets the neck.
- Behind the jaw, the neck keeps a faint grey shadow where the profile picture's hair was cleared from the skin.
- The front-left crown keeps some dark smear: those surfaces face sideways,
  not up, so the crown fill does not reach them.
- Hair is a painted shell, not cards or strands.
- The head only: body, hands and rig integration are separate stages.
