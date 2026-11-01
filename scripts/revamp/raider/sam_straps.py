import sys, numpy as np, cv2
from segment_anything import sam_model_registry, SamPredictor
ref, ckpt, out = sys.argv[1], sys.argv[2], sys.argv[3]
img = cv2.cvtColor(cv2.imread(ref), cv2.COLOR_BGR2RGB)
part = np.load(out + "/parts-v2.npy").astype(object)
pred = SamPredictor(sam_model_registry["vit_b"](checkpoint=ckpt).to("cuda")); pred.set_image(img)
pts = [(385, 415), (400, 410), (415, 450), (510, 415), (535, 430), (600, 460), (470, 500), (465, 520), (577, 500)]
union = np.zeros(part.shape, bool)
for p in pts:
    m, s, _ = pred.predict(point_coords=np.array([p], float), point_labels=np.array([1]), multimask_output=True)
    # smallest confident mask that is leather-sized, not the whole torso
    cands = [(mk.sum(), sc, mk) for mk, sc in zip(m, s) if 300 < mk.sum() < 8000 and sc > 0.5]
    if not cands: print("skip", p, [int(mk.sum()) for mk in m]); continue
    a, sc, mk = max(cands, key=lambda c: c[1])
    print("strap", p, int(a), round(float(sc), 2)); union |= mk
take = union & np.isin(part, ["jacket", "trousers"])
part[take] = "strap"
np.save(out + "/parts-v3.npy", part.astype("U12"))
old = np.load(out + "/parts-v2.npy")
vis = img.copy(); vis[take] = (0.3 * vis[take] + 0.7 * np.array([255, 60, 0])).astype(np.uint8)
c = vis[180:720, 300:720]; cv2.imwrite(out + "/straps-added.png", cv2.cvtColor(cv2.resize(c, None, fx=1.5, fy=1.5), cv2.COLOR_RGB2BGR))
print("moved_to_strap_px", int(take.sum()))
