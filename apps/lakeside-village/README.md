# Stillwater

A Three.js lakeside village composed from seven independently generated
assets, with a separate orbit inspector. The public showcase explains the
Reference Asset Compiler workflow, credits the creator and tools, and links to
the project and pipeline documentation. This scene demo is outside the UE
production cohort.

## Run

From this directory, run `./start.ps1`, or `npm ci` followed by `npm run dev`.
Open <http://127.0.0.1:5178/>. `npm run build` makes a static `dist/` directory.
The preserved pre-publication bundle is `../../out/stillwater-threejs-cleanup-v3-2026-09-15.zip`;
the original and composition-v2 bundles are preserved.
Extract it and serve its folder with any static HTTP server; opening HTML with
`file://` cannot load the GLB assets because browsers require HTTP for these files.
After dependencies are installed, all runtime models, images, fonts and code
are local; the page makes no external network requests.

- Drag the scene to orbit; scroll to zoom; right-drag to pan.
- Choose **Reference view**, **The village**, or **Overlook** to reset the scene camera.
  Reference view is also the arrival view. It restores position, target, field
  of view and zoom after exploration, clearing residual orbit momentum.
- Click an object in the scene or a collection thumbnail to inspect that asset.
- Drag and zoom inside the right panel independently. Auto rotate, wireframe,
  source reference, reset view and individual GLB downloads are available.
- **Pause** stops water, boats, chimney smoke and hearth light animation.
  Asset auto rotation has its own switch.
- The panels stack on narrow screens.

## Public showcase

Live at [markbhall.dev/stillwater](https://markbhall.dev/stillwater/).
The **How it was made** section explains the separate reference, AI geometry,
Blender cleanup, AI painting and Three.js assembly steps. The header and story
link to [Reference Asset Compiler](https://github.com/raydeStar/reference-asset-compiler)
and the pipeline/playbook. Finished GLBs load in the visitor's browser; inference
ran beforehand on the workstation.

The existing `raydeStar/markbhall.dev` repository publishes its
`static/stillwater/` directory through Hugo and GitHub Pages. To update it, build
this app, copy `dist/index.html`, `dist/reference.png`, `dist/reference.webp`,
`dist/stillwater-*.jpg`, `dist/stillwater-*.webp`, runtime `dist/assets/`
and `dist/licenses/`, and refresh the public `release.json` hashes. Exclude the
internal `review.html`, `review/` sheets and `assets/review-*.js`. Retire only
superseded generated entry files. The relative Vite base (`./`) keeps model,
image and download paths valid under `/stillwater/` as well as localhost.

The current publication commit, deployment and exact public-byte verification
are recorded in `../../docs/STATUS.md`. The main project's
editable source remains in this working checkout; publication committed the
standalone runtime to the personal site's repository. Evidence is under
`../../work/lakeside-village/evidence/pages-2026-09-15/`.

### Web delivery and social previews

After restoring accepted assets, run `node prepare_web_assets.mjs` before
`npm run build`. It verifies all seven original hashes and makes `.web.glb`
derivatives with 1024px WebP textures, preserving every non-image buffer byte.
`web-asset-manifest.json` records the original and derivative hashes. Original
GLBs remain available through **Download original GLB**; the scene and inspector
share the lighter model library. The inspector initializes when visible, and
rendering pauses for offscreen panels. Full-size reference PNGs load on demand.

The 1200 × 627 social JPEG and scene poster are actual WebGL screenshots. To
recapture, serve the build at `/?capture=card` or `/?capture=scene`, use a
1200 × 627 viewport, and wait for all seven assets before saving a screenshot.
The 720px homepage teaser is a smaller WebP of the same scene. These captures
are retained in `../../work/lakeside-village/evidence/performance-v1/`.

That folder also retains the before/after network reports and independent
geometry audit. `network_preview.py` serves a disposable static build through
a shared 2 Mbps / 150 ms limiter with gzip and no cache. Its reporting probe
is local-only and is never included in the public build. Use server-observed
milestone times; this is a desktop-GPU network/viewport check, not a physical
phone or CPU-throttled benchmark.

## Assets and provenance

`asset-manifest.json` records the delivered GLB hashes, exact triangle counts,
embedded textures, and independent geometry comparisons against the UV inputs.
`prompts.json` retains the seven image-generation prompts; `ground-prompt.txt`
records the additional forest-floor material prompt. Image references were made
with the built-in image generator, conditioned on the user-supplied village image.
Each isolated reference then conditioned the repository's pinned Hunyuan3D-2
single-view geometry runner (seed 42, 30 steps, octree 512). Blender made
reviewable browser derivatives and UV layouts. Hunyuan3D-Paint 2.1 produced
six-view, 512-resolution reference-conditioned materials on those exact meshes.

Large generated files are deliberately local and ignored by Git:

- Original scene: `../../work/lakeside-village/references/scene-original.png`.
- Each asset: `../../work/lakeside-<id>/` contains the intake, AI candidate,
  fixed modeling views, retained preview, UV input, paint output and reviews.
- Texture authority: `paint-v1/painted.glb`, except the cleaned tree uses
  `paint-v2/painted.glb`. Copy those into `public/assets/<id>.glb` to restore.
- Copy `references/primary.png` into `public/assets/<id>.png` and the original
  scene to `public/reference.png`. Restore ground material and review images
  from the local demo bundle or retained references.

The user explicitly delegated modeling, topology and texture visual review for
this demo. `demo-reviews/` retains hash-bound authorization and actual review
receipts; these do not certify the separate UE production contracts. Unseen
sides are AI inferences from single images, and the tree is stylized foliage.
On 2026-09-15 the user also explicitly accepted all seven delivered assets;
`work/lakeside-village/evidence/user-asset-acceptance-2026-09-15.json` binds
that acceptance to the unchanged delivered GLB hashes.

The second scene pass follows the original composition more closely: a rounded
inlet, winding foreground path, dock and two boats, forest framing, calmer gold
reflections, cloud bands, warm porch lights and chimney smoke. Procedural grass,
low fern-like ground cover and flower flecks dress the terrain. Scene-only tree
instances use narrower X/Z scales (0.65-0.67); their inspector and download retain
the accepted original proportions. Terrain, atmosphere and placement are scene
staging; the seven object meshes remain the reference-conditioned AI authorities.
The reference camera is an interpreted composition, not a pixel-perfect image
reconstruction. Fine pine branches, mountain detail and painterly clouds remain
the most visible differences from the source.

The final cleanup seats each tree's root area against actual terrain triangles,
instead of positioning its lowest root tip at the terrain formula's height.
Dock landings derive from the shore curve and the mesh's broad plank surface;
both docks overlap dry land. Each asset group has an independent random seed,
so changes to ground cover cannot shuffle the forest. The asset files are untouched.

The first tree preview contained 92 detached fragments. `repair_tree.py` removed
101 triangles, preserved the main component, and retained the rejected version.
Its old paint plan was cancelled before inference. The served, painted tree is
checked again for one connected component after UV vertices are merged.

The Windows painter has exited abnormally during teardown after saving its
outputs. Clean process exit and artifact validity are recorded separately.
There are no blind inference retries. Each accepted GLB is independently loaded,
rendered from four views and compared with its input geometry and UV receipt.

## Verification

`audit_assets.py` verifies actual served bytes, UV completeness, embedded albedo,
triangle counts, symmetric triangle-center distance below 1e-6, painter checks,
and the tree's connected component. Use the repository's Python environment.
The app build and browser interaction checks are recorded in the dated handoff.
The compiler's existing test suite remains separate from this scene's visual QA.
`node audit_placement.mjs <new-report.json>` runs the current scene layout on CPU
using the accepted GLB geometry, without decoding textures. It independently
measures root-to-terrain gaps and raycasts both deck and terrain at each landing.
Reports refuse to overwrite an existing file. Final results are retained under
`../../work/lakeside-village/evidence/cleanup-v3/`.

Core browser APIs: [GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html),
[OrbitControls](https://threejs.org/docs/pages/OrbitControls.html), and
[Water](https://threejs.org/docs/pages/Water.html). Fonts are bundled from the
Fontsource packages with licenses included under `public/licenses/` and in the
static build.
