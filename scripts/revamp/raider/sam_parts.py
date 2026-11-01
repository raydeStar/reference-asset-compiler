import sys, json, numpy as np, torch, cv2
from segment_anything import sam_model_registry, SamPredictor
ref, ckpt, out = sys.argv[1], sys.argv[2], sys.argv[3]
img = cv2.cvtColor(cv2.imread(ref), cv2.COLOR_BGR2RGB); H, W = img.shape[:2]
auto = np.load(out + "/labels.npy")
fg = ~(img.astype(int).sum(-1) > 735)
# automatic ids -> parts (read off ids.png)
A = {"hair": [23], "face": [6], "beard": [36], "skin": [26, 25],
     "sleeve_roll": [27, 29, 0], "plate": [12, 17, 16, 8], "pouch": [20, 15, 37], "buckle": [30], "belt": [39],
     "strap": [31, 38, 28, 40], "kneepad": [19, 11, 18, 10, 49], "glove": [9, 45, 24, 47, 42, 44],
     "boot": [7, 13, 35, 5, 14, 34], "boot_strap": [48, 33, 43, 41, 32, 46], "trousers": [4, 2, 21, 22]}
part = np.full((H, W), "", object)
pred = SamPredictor(sam_model_registry["vit_b"](checkpoint=ckpt).to("cuda")); pred.set_image(img)
def prompt(pos, neg=()):
    pts = np.array(list(pos) + list(neg), float); lab = np.array([1] * len(pos) + [0] * len(neg))
    m, s, _ = pred.predict(point_coords=pts, point_labels=lab, multimask_output=True)
    return m[int(np.argmax(s))]
P = {  # dark, low-contrast parts the automatic pass missed
  "jacket": [([240, 420], [700, 430], [620, 650], [300, 470]), ([330, 280], [600, 380], [510, 545], [510, 160])],
  "glove": [([880, 690], [850, 610]), ([790, 520],)],
  "thigh_pouch": [([328, 750],), ([425, 790],)],
  "strap": [([425, 300], [455, 420]), ([500, 330],)],
  "trousers": [([455, 880], [560, 790]), ([380, 980], [430, 790])],
  "shirt": [([505, 265],), ([540, 330], [420, 200])],
}
order = ["jacket", "shirt", "trousers", "glove", "thigh_pouch", "strap"]
for name in order:
    for pos, neg in [P[name]] if isinstance(P[name], tuple) else [P[name]]:
        m = prompt(pos, neg) & fg
        part[m & (auto < 0) | (m & (part == ""))] = name
for name, ids in A.items():
    for k in ids: part[auto == k] = name
part[~fg] = ""
names = sorted({p for p in part.ravel() if p})
pal = {"hair": (70,35,15), "face": (240,180,140), "beard": (120,70,40), "skin": (215,140,100), "sleeve_roll": (40,150,170),
       "jacket": (25,140,165), "shirt": (60,90,110), "plate": (215,215,230), "pouch": (230,205,80), "buckle": (255,240,120),
       "belt": (200,100,40), "strap": (205,90,40), "kneepad": (240,115,180), "glove": (140,50,155), "boot": (140,75,25),
       "boot_strap": (190,120,60), "trousers": (75,75,90), "thigh_pouch": (250,170,60)}
vis = np.full((H, W, 3), 90, np.uint8)
for n in names: vis[part == n] = pal.get(n, (255, 0, 0))
unl = fg & (part == ""); vis[unl] = (255, 0, 0)
cv2.imwrite(out + "/parts.png", cv2.cvtColor(vis, cv2.COLOR_RGB2BGR))
np.save(out + "/parts.npy", part.astype("U12"))
print("PARTS", {n: int((part == n).sum()) for n in names}, "unlabelled", int(unl.sum()), "of", int(fg.sum()))
