import sys, numpy as np, torch, cv2
from segment_anything import sam_model_registry, SamPredictor
ref, ckpt, out = sys.argv[1], sys.argv[2], sys.argv[3]
img = cv2.cvtColor(cv2.imread(ref), cv2.COLOR_BGR2RGB); H, W = img.shape[:2]
part = np.load(out + "/parts.npy").astype(object)
fg = ~(img.astype(int).sum(-1) > 735)
pred = SamPredictor(sam_model_registry["vit_b"](checkpoint=ckpt).to("cuda")); pred.set_image(img)
m, s, _ = pred.predict(box=np.array([300, 695, 372, 852]), multimask_output=True)
pouch = m[int(np.argmax(s))] & fg
part[pouch & np.isin(part, ["", "trousers", "strap", "thigh_pouch"])] = "thigh_pouch"
# jacket hem: per column, the jacket covers cloth above the hem line of the reference (left 672 -> right 692)
ys, xs = np.mgrid[0:H, 0:W]
hem = 672 + (xs - 330) * (20 / 340.0)
cloth = np.isin(part, ["trousers", "jacket", "shirt"])
arms = (xs < 330) | (xs > 690)
part[cloth & ((ys < hem) | (arms & (ys < 560)))] = "jacket"
# fill unlabelled foreground from nearest labelled pixel
names = sorted({p for p in part.ravel() if p}); idx = {n: i for i, n in enumerate(names)}
lab = np.vectorize(lambda p: idx.get(p, -1))(part).astype(np.int32)
unl = fg & (lab < 0)
_, nn = cv2.distanceTransformWithLabels((lab < 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
seed = np.zeros(nn.max() + 1, np.int32); yy, xx = np.nonzero(lab >= 0); seed[nn[yy, xx]] = lab[yy, xx]
lab[unl] = seed[nn[unl]]
part = np.where(lab >= 0, np.array(names, object)[np.clip(lab, 0, None)], "")
part[~fg] = ""
pal = {"hair": (70,35,15), "face": (240,180,140), "beard": (120,70,40), "skin": (215,140,100), "sleeve_roll": (40,150,170),
       "jacket": (25,120,150), "shirt": (60,90,110), "plate": (215,215,230), "pouch": (230,205,80), "buckle": (255,240,120),
       "belt": (200,100,40), "strap": (205,90,40), "kneepad": (240,115,180), "glove": (140,50,155), "boot": (140,75,25),
       "boot_strap": (190,120,60), "trousers": (85,85,100), "thigh_pouch": (250,170,60)}
vis = np.full((H, W, 3), 90, np.uint8)
for n in names: vis[part == n] = pal[n]
side = np.concatenate([img, vis], 1)
for n, (x, y) in {"hair": (600, 40), "face": (600, 120), "plate": (110, 260), "strap": (700, 250), "jacket": (790, 420), "pouch": (690, 560),
                  "buckle": (560, 610), "glove": (840, 820), "thigh_pouch": (150, 770), "trousers": (750, 900), "kneepad": (720, 990), "boot": (790, 1400), "boot_strap": (790, 1250), "skin": (850, 500), "sleeve_roll": (850, 460), "beard": (600, 170)}.items():
    cv2.putText(side, n, (W + x, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
cv2.imwrite(out + "/parts-v2.png", cv2.cvtColor(side, cv2.COLOR_RGB2BGR))
np.save(out + "/parts-v2.npy", part.astype("U12"))
print("PARTS", {n: int((part == n).sum()) for n in names})
