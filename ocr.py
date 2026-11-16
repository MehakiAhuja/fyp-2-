import cv2, re, torch
from PIL import Image
from transformers import TrOCRProcessor, VisionEncoderDecoderModel
from detector import DEVICE

MODEL_DIR = "models/trocr/best_finetuned_model"
PROC_DIR = "models/trocr/meter-trocr-model-v3"      # keep this folder, the processor is loaded from here


def load_ocr(path=MODEL_DIR, proc_path=PROC_DIR):
    proc = TrOCRProcessor.from_pretrained(proc_path)
    model = VisionEncoderDecoderModel.from_pretrained(path).to(DEVICE).eval()
    return proc, model


def _pixels(proc, crop_bgr):
    pil = Image.fromarray(cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB))
    return proc(images=pil, return_tensors="pt").pixel_values.to(DEVICE)


@torch.no_grad()
def read_text(proc, model, crop_bgr):
    ids = model.generate(_pixels(proc, crop_bgr), num_beams=1, do_sample=False,
                         max_new_tokens=14, use_cache=True)
    txt = proc.batch_decode(ids, skip_special_tokens=True)[0]
    return re.sub(r"[^0-9.]", "", txt)