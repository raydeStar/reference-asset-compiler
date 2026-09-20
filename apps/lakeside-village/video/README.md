# Stillwater short showcase

Capture and edit a 23.5-second, 1920 × 1080, 30 FPS silent MP4 from the actual
Three.js scene, accepted assets and source images. The local Vite plugin changes
only the in-memory capture route. It leaves the public scene source, GLBs and
deployed site unchanged.

## Commands

Run from the repository root, after restoring the app's local public assets and
installing its npm dependencies:

```powershell
node apps/lakeside-village/video/inspect.mjs
node apps/lakeside-village/video/render.mjs --preview
node apps/lakeside-village/video/render.mjs
python apps/lakeside-village/video/verify_video.py
node apps/lakeside-village/video/playback_check.mjs
```

Requirements: the installed Chrome browser, FFmpeg/FFprobe on PATH, Python with
NumPy and Pillow, and Playwright from the workstation's bundled Node runtime.
The Playwright path is explicit in the scripts; update it for another machine.
Rendering uses the existing GPU via ANGLE/D3D11 and never starts AI inference.
The render script refuses to overwrite the delivered MP4; retain an old version
and change the output directory when making a new edit.

## Direction

| Time | Shot |
|---|---|
| 0–3.3 s | Finished world, gentle camera move, small opening title |
| 3.3–5.1 s | Actual supplied source image and seven isolated references |
| 5.1–8.2 s | Closer view of the village shore |
| 8.2–10.8 s | Timber cabin in the enlarged real asset inspector |
| 10.8–12.0 s | Actual Wireframe control enabled; rotation continues |
| 12.0–14.1 s | Actual Reference action; source and model visible together |
| 14.1–19.0 s | Four workflow stages, enlarged and summarized for video |
| 19.0–23.5 s | Return to the lake, project/URL caption, clean fade |

`director.js` advances the real scene animation and camera one exact 1/30-second
step per captured frame. Browser screenshots feed FFmpeg directly, so expensive
frames do not become playback stutters. `film.css` reframes existing UI for
1080p legibility; the workflow copy is shortened in the capture context only.
Original shader animation, scene placement, lighting, models, materials and
references are retained. There is no synthesized video, stock footage or fake
terminal. The GLB audit caption refers to the retained geometry/UV/material
checks; it is not a UE production-readiness claim.

## Delivery and evidence

- MP4 and optional upload cover: `out/stillwater-showcase-2026-09-16/`.
- Live-site inspection, shot previews, decoded-video contact sheet, capture
  hashes, timing/motion checks and browser playback receipt:
  `work/lakeside-village/evidence/showcase-video-v1/`.
- Encoding: H.264 High, CRF 18, yuv420p, square pixels, 30 FPS, fast-start MP4.
- `verify_video.py` decodes all 705 frames, checks constant timestamps and MP4
  atom ordering, rejects repeated frames within directed motion, and extracts
  review stills from the actual finished video.

The first layout preview was rejected because Vite inserted the app stylesheet
after the capture overrides. Its images are retained in `layout-draft-1/`.
Capture overrides now load after the app styles. No capture code was published
to the website and no LinkedIn post was created.
