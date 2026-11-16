import cv2
import numpy as np


def needs_enhancement(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    mean, std = float(gray.mean()), float(gray.std())
    return std < 40 or mean < 80 or mean > 180


def enhance_crop(crop):
    out = np.empty_like(crop)
    for c in range(3):
        lo, hi = np.percentile(crop[:, :, c], (2, 98))
        if hi - lo < 1:
            out[:, :, c] = crop[:, :, c]
        else:
            out[:, :, c] = np.clip(
                (crop[:, :, c].astype(np.float32) - lo) * 255.0 / (hi - lo), 0, 255
            ).astype(np.uint8)
    return out