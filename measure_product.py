import re, sys, time
import cv2
import pandas as pd
from engine import read_meter, get_pipe

IMG_DIR = r"..\digitronix\test_images"
LABELS = r"..\digitronix\test_images\labels.csv"
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

get_pipe()
rows = []
for n, (f, gt) in enumerate(items, 1):
    img = cv2.imread(IMG_DIR + "\\" + f)
    if img is None:
        continue
    t = time.perf_counter()
    res = read_meter(img)
    sec = time.perf_counter() - t
    pred = norm(res["reading"]) if res["ok"] else ""
    rows.append({"file": f, "gt": gt, "pred": pred, "readable": int(res["ok"]),
                 "exact": int(pred == gt), "char_acc": max(0, 1 - lev(pred, gt) / max(len(gt), 1)),
                 "seconds": sec})
    print(f"[{n}/{len(items)}] {f}")

df = pd.DataFrame(rows)
df.to_csv("product_metrics.csv", index=False)
s = df["seconds"].sort_values().reset_index(drop=True)
print("\n===== PRODUCT METRICS =====")
print("Images tested        :", len(df))
print(f"Readable rate        : {df.readable.mean() * 100:.2f}%")
print(f"Exact accuracy       : {df.exact.mean() * 100:.2f}%")
print(f"Character accuracy   : {df.char_acc.mean() * 100:.2f}%")
print(f"Avg time / image     : {df.seconds.mean():.2f} s")
print(f"Median time          : {df.seconds.median():.2f} s")
print(f"90th percentile time : {s.iloc[int(len(s) * 0.9) - 1]:.2f} s")