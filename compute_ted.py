import pandas as pd


def lev(a, b):
    dp = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, dp[0] = dp[0], i
        for j, cb in enumerate(b, 1):
            prev, dp[j] = dp[j], min(dp[j] + 1, dp[j - 1] + 1, prev + (ca != cb))
    return dp[-1]


df = pd.read_csv("product_metrics.csv", dtype={"gt": str, "pred": str}).fillna("")
d = [lev(p, g) for p, g in zip(df["pred"], df["gt"])]
chars = sum(len(g) for g in df["gt"])

print("===== PRODUCT: ACCURACY, CER, TED =====")
print("Images                      :", len(df))
print(f"Overall accuracy (exact)    : {df['exact'].mean() * 100:.2f}%")
print(f"CER (total edits / chars)   : {sum(d) / chars * 100:.2f}%")
print(f"TED (avg edits per image)   : {sum(d) / len(d):.4f}")