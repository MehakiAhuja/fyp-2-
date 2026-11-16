import time
import cv2
import numpy as np
from PIL import Image, ImageEnhance
from detector import load_detector, detect
from ocr import load_ocr, read_text

PAD = 4
CONTRAST = 1.10          # same preprocessing the friend model was trained with


def apply_contrast(crop_bgr):
    pil = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
    pil = ImageEnhance.Contrast(pil).enhance(CONTRAST)
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


class MeterPipeline:
    def __init__(self):
        self.det = load_detector()
        self.proc, self.ocr = load_ocr()

    def run(self, img_bgr, use_preprocessing=True):
        t0 = time.perf_counter()
        dets = detect(self.det, img_bgr)          # detection on the original image
        t1 = time.perf_counter()
        h, w = img_bgr.shape[:2]
        for d in dets:
            x1, y1, x2, y2 = d["box"]
            crop = img_bgr[max(0, y1 - PAD):min(h, y2 + PAD), max(0, x1 - PAD):min(w, x2 + PAD)]
            d["enhanced"] = bool(use_preprocessing)
            if crop.size == 0:
                d["text"] = ""
                continue
            if use_preprocessing:
                crop = apply_contrast(crop)
            d["text"] = read_text(self.proc, self.ocr, crop)
        t2 = time.perf_counter()
        return {
            "mode": "with_preprocessing" if use_preprocessing else "without_preprocessing",
            "results": dets,
            "time": {"preprocess": 0.0, "detection": round(t1 - t0, 3),
                     "ocr": round(t2 - t1, 3), "total": round(t2 - t0, 3)},
        }