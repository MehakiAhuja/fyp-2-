import cv2, torch
from torchvision.models.detection import fasterrcnn_resnet50_fpn
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
import torchvision.transforms.functional as F

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
NUM_CLASSES = 2
CLASS_NAMES = {1: "meter_reading"}

def load_detector(path="models/final_model.pth"):
    model = fasterrcnn_resnet50_fpn(weights=None, weights_backbone=None)
    in_f = model.roi_heads.box_predictor.cls_score.in_features
    model.roi_heads.box_predictor = FastRCNNPredictor(in_f, NUM_CLASSES)
    ck = torch.load(path, map_location=DEVICE)
    model.load_state_dict(ck.get("model_state_dict", ck) if isinstance(ck, dict) else ck)
    return model.to(DEVICE).eval()

@torch.no_grad()
def detect(model, img_bgr, thr=0.5):
    t = F.to_tensor(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)).to(DEVICE)
    out = model([t])[0]
    dets = []
    for b, l, s in zip(out["boxes"].cpu().numpy(), out["labels"].cpu().numpy(), out["scores"].cpu().numpy()):
        if s >= thr:
            dets.append({"box": [int(x) for x in b],
                         "label": CLASS_NAMES.get(int(l), str(int(l))),
                         "score": round(float(s), 3)})
    return dets