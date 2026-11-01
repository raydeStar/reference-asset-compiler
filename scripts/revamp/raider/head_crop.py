"""Crop the head from the reference (box from the Segment Anything hair/face/beard labels) and upscale it 4x
with Real-ESRGAN (BSD-3) for a head-only image-conditioned acquisition."""
import sys, json, numpy as np, torch
from PIL import Image
import spandrel
ref, model_p, out = sys.argv[1:4]
# head box in reference fractions, checked on the face sheet: hair top to collar, ear to ear with margin
W0, H0 = Image.open(ref).size
side = int(W0 * 0.30); top_pad = int(side * 0.08); x0 = int(W0 * 0.5 - side / 2)
box = (x0, 0, x0 + side, side - top_pad)
im = Image.open(ref).convert("RGB"); W, H = im.size
canvas = Image.new("RGB", (side, side), (255, 255, 255)); canvas.paste(im.crop(box), (0, top_pad))
print("BOX", box, "side", side)
model = spandrel.ModelLoader().load_from_file(model_p).cuda().eval()
x = torch.from_numpy(np.asarray(canvas).astype(np.float32) / 255).permute(2, 0, 1)[None].cuda()
with torch.no_grad(): y = model(x).clamp(0, 1)
up = Image.fromarray((y[0].permute(1, 2, 0).cpu().numpy() * 255).round().astype(np.uint8))
up.save(out); print("UP", up.size)
json.dump({"source": ref, "box": box, "upscaler": "RealESRGAN_x4.pth", "scale": 4}, open(out + ".json", "w"), indent=2)
