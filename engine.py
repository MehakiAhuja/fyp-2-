import cv2
import numpy as np
from pipeline import MeterPipeline

_pipe = None


def get_pipe():
    global _pipe
    if _pipe is None:
        _pipe = MeterPipeline()
        dummy = np.zeros((300, 500, 3), dtype=np.uint8)
        _pipe.run(dummy, True)          # warm-up
    return _pipe


def read_meter(img_bgr):
    h, w = img_bgr.shape[:2]
    if max(h, w) > 1000:
        s = 1000 / max(h, w)
        img_bgr = cv2.resize(img_bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    out = get_pipe().run(img_bgr, True)
    dets = [d for d in out["results"] if d["label"] == "meter_reading"]
    if not dets:
        return {"ok": False, "reading": None, "confidence": 0, "seconds": out["time"]["total"],
                "message": "No meter reading found. Please retake the photo."}
    best = max(dets, key=lambda d: d["score"])
    text = best["text"].strip(".")
    try:
        float(text)
    except ValueError:
        return {"ok": False, "reading": None, "confidence": round(best["score"] * 100),
                "seconds": out["time"]["total"],
                "message": "The reading could not be read clearly. Please retake the photo."}
    return {"ok": True, "reading": text, "confidence": round(best["score"] * 100),
            "seconds": out["time"]["total"], "message": ""}