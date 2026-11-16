import os, re, sys, time, gc
import cv2
import torch
import pandas as pd
import transformers
from PIL import Image, ImageEnhance
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from detector import load_detector, detect, DEVICE

transformers.logging.set_verbosity_error()

IMG_DIR = r"..\digitronix\test_images"
LABELS = r"..\digitronix\test_images\labels.csv"
V3 = "models/trocr/meter-trocr-model-v3"
FRIEND = "models/trocr/best_finetuned_model"
PAD = 4
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else None


def norm(s):
    s = re.sub(r"[^0-9.]", "", str(s))
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    s = s.lstrip("0")
    return "0" + s if s.startswith(".") else s


def lev(a, b):
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, cb in enumerate(b, 1):
            prev, dp[j] = dp[j], min(dp[j] + 1, dp[j - 1] + 1, prev + (ca != cb))
    return dp[-1]


pat = re.compile(r"^\s*([^\s,;]+\.(?:jpg|jpeg|png))[\s,;]+(.+?)\s*$", re.IGNORECASE)
items = []
with open(LABELS, encoding="utf-8-sig") as fh:
    for line in fh:
        m = pat.match(line)
        if m:
            items.append((m.group(1), norm(m.group(2))))
if LIMIT:
    items = items[:LIMIT]

# Phase 1: detect and crop once, so both models read exactly the same crops
det = load_detector()
crops = []
for n, (f, gt) in enumerate(items, 1):
    img = cv2.imread(os.path.join(IMG_DIR, f))
    crop = None
    if img is not None:
        h, w = img.shape[:2]
        if max(h, w) > 1000:
            s = 1000 / max(h, w)
            img = cv2.resize(img, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
            h, w = img.shape[:2]
        dets = [d for d in detect(det, img) if d["label"] == "meter_reading"]
        if dets:
            x1, y1, x2, y2 = max(dets, key=lambda d: d["score"])["box"]
            c = img[max(0, y1 - PAD):min(h, y2 + PAD), max(0, x1 - PAD):min(w, x2 + PAD)]
            crop = c if c.size else None
    crops.append((f, gt, crop))
    print(f"[detect {n}/{len(items)}] {f}")
del det
gc.collect()

# Same processor for both models (both use 384x384, mean/std 0.5, same RoBERTa vocabulary)
proc = TrOCRProcessor.from_pretrained(V3)


def evaluate(model_dir, contrast):
    model = VisionEncoderDecoderModel.from_pretrained(model_dir).to(DEVICE).eval()
    preds, secs = [], []
    for n, (f, gt, crop) in enumerate(crops, 1):
        if crop is None:
            preds.append("")
            continue
        pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        if contrast:
            pil = ImageEnhance.Contrast(pil).enhance(contrast)
        t = time.perf_counter()
        with torch.no_grad():
            pv = proc(images=pil, return_tensors="pt").pixel_values.to(DEVICE)
            ids = model.generate(pv, num_beams=1, do_sample=False, max_new_tokens=14, use_cache=True)
        secs.append(time.perf_counter() - t)
        preds.append(norm(proc.batch_decode(ids, skip_special_tokens=True)[0]))
        print(f"[{os.path.basename(model_dir)} {n}/{len(crops)}] {f}")
    del model
    gc.collect()
    return preds, secs[1:] if len(secs) > 1 else secs


p1, s1 = evaluate(V3, None)
p2, s2 = evaluate(FRIEND, 1.10)

gts = [g for _, g, _ in crops]
pd.DataFrame({"file": [f for f, _, _ in crops], "gt": gts, "current_v3": p1, "friend_contrast110": p2}) \
    .to_csv("compare_models.csv", index=False)

print("\n===== MODEL COMPARISON (same crops, images tested:", len(crops), ") =====")
for name, preds, secs in (("Current model v3 (raw crop)", p1, s1), ("Friend model (contrast 1.10)", p2, s2)):
    d = [lev(p, g) for p, g in zip(preds, gts)]
    exact = sum(p == g for p, g in zip(preds, gts))
    print(f"\n{name}")
    print(f"  Exact accuracy : {exact}/{len(gts)} = {exact / len(gts) * 100:.2f}%")
    print(f"  CER            : {sum(d) / sum(len(g) for g in gts) * 100:.2f}%")
    print(f"  TED (avg edits): {sum(d) / len(d):.4f}")
    print(f"  Avg OCR time   : {sum(secs) / max(len(secs), 1):.2f} s per crop")