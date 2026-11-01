import sys, json, numpy as np, torch, cv2
from segment_anything import sam_model_registry, SamAutomaticMaskGenerator
ref, ckpt, out = sys.argv[1], sys.argv[2], sys.argv[3]
img = cv2.cvtColor(cv2.imread(ref), cv2.COLOR_BGR2RGB)
sam = sam_model_registry["vit_b"](checkpoint=ckpt).to("cuda" if torch.cuda.is_available() else "cpu")
gen = SamAutomaticMaskGenerator(sam, points_per_side=48, pred_iou_thresh=0.86, stability_score_thresh=0.9, min_mask_region_area=150)
masks = gen.generate(img)
masks.sort(key=lambda m: -m["area"])
H, W = img.shape[:2]
# drop the white background
fg = ~((img.astype(int).sum(-1) > 735))
label = np.full((H, W), -1, np.int32)
kept = []
for m in masks:
    seg = m["segmentation"] & fg
    if seg.sum() < 150 or seg.sum() > 0.5 * fg.sum(): continue
    k = len(kept); kept.append(m); label[seg] = k   # smaller masks painted later win
np.save(out + "/labels.npy", label)
rng = np.random.default_rng(3); cols = rng.integers(40, 255, (len(kept), 3))
vis = (img * 0.35).astype(np.uint8)
for k in range(len(kept)):
    vis[label == k] = (0.55 * cols[k] + 0.45 * img[label == k]).astype(np.uint8)
for k in range(len(kept)):
    ys, xs = np.nonzero(label == k)
    if len(xs) < 300: continue
    cy, cx = int(np.median(ys)), int(np.median(xs))
    if label[cy, cx] != k:
        i = len(xs) // 2; cy, cx = ys[i], xs[i]
    cv2.putText(vis, str(k), (cx - 8, cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
    cv2.putText(vis, str(k), (cx - 8, cy + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
cv2.imwrite(out + "/ids.png", cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))
print("SAM_MASKS", len(masks), "kept", len(kept), "unlabelled_fg", int(((label < 0) & fg).sum()))
