# evaluate.py — KcELECTRA-base 저장 모델로 로컬 데이터 평가 리포트 생성
import os, json, numpy as np, pandas as pd, torch, matplotlib
from pathlib import Path
matplotlib.use("Agg")  # GUI 없이 PNG 저장
import matplotlib.pyplot as plt
from sklearn.model_selection import train_test_split
from sklearn.metrics import (classification_report, confusion_matrix,
                             accuracy_score, f1_score, precision_recall_fscore_support)
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import platform
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np

# ▶ 한글 폰트 지정 (Windows: 맑은 고딕, 그 외: 나눔고딕)
if platform.system() == "Windows":
    mpl.rcParams["font.family"] = "Malgun Gothic"
else:
    mpl.rcParams["font.family"] = "NanumGothic"

# 마이너스 기호 깨짐 방지
mpl.rcParams["axes.unicode_minus"] = False

# === 0) 경로 설정 (로컬 Windows 경로) =========================================
ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = os.getenv("EMO_MODEL_DIR", str(ROOT / "kc_saved_model"))
CSV_PATH = os.getenv("EMOTION_DATA_CSV", str(ROOT / "data" / "sample_emotion_data.csv"))

MAX_LEN = 128
BATCH   = 64

# === 1) 데이터 로드 (인코딩 자동 판별) =========================================
try:
    df = pd.read_csv(CSV_PATH)
except UnicodeDecodeError:
    for enc in ["utf-8-sig", "cp949", "euc-kr"]:
        try:
            df = pd.read_csv(CSV_PATH, encoding=enc)
            break
        except Exception:
            pass
    else:
        raise

assert {"text","stage2"} <= set(df.columns), "CSV에 text, stage2 컬럼이 필요합니다."
df = df[["text","stage2"]].dropna().reset_index(drop=True)

# === 2) 모델/토크나이저 로드 ===================================================
tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
model     = AutoModelForSequenceClassification.from_pretrained(MODEL_DIR)
model.eval()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# CPU만 쓰는 서버면 다음 줄로 스레드 제한 가능: torch.set_num_threads(1)
model.to(device)

with open(os.path.join(MODEL_DIR, "id2label.json"), encoding="utf-8") as f:
    id2label = {int(k): v for k, v in json.load(f).items()}
label2id = {v:k for k,v in id2label.items()}
labels_order = [id2label[i] for i in range(len(id2label))]

# stage1 매핑(긍정/부정)
positive_set = {"기쁨", "놀람"}
def to_stage1(lbl): return "긍정" if lbl in positive_set else "부정"

# === 3) 학습/검증 분할(재현성 고정) ============================================
train_df, test_df = train_test_split(df, test_size=0.15, random_state=42, stratify=df["stage2"])

# === 4) 배치 추론 ==============================================================
def batch_iter(iterable, n=BATCH):
    L = len(iterable)
    for i in range(0, L, n):
        yield iterable[i:i+n]

texts = test_df["text"].tolist()
y_true_lbl = test_df["stage2"].tolist()
y_true = np.array([label2id[l] for l in y_true_lbl], dtype=int)

all_probs, all_preds = [], []
with torch.no_grad():
    for chunk in batch_iter(texts, BATCH):
        enc = tokenizer(chunk, return_tensors="pt", truncation=True, padding=True, max_length=MAX_LEN)
        enc = {k: v.to(device) for k, v in enc.items()}
        logits = model(**enc).logits
        probs  = torch.softmax(logits, dim=-1).cpu().numpy()
        preds  = probs.argmax(axis=-1)
        all_probs.append(probs); all_preds.append(preds)

y_prob = np.vstack(all_probs)
y_pred = np.concatenate(all_preds)

# === 5) 6-클래스 지표 ==========================================================
cls_report = classification_report(y_true, y_pred, target_names=labels_order, output_dict=True, zero_division=0)
acc  = accuracy_score(y_true, y_pred)
f1m  = f1_score(y_true, y_pred, average="macro")
f1w  = f1_score(y_true, y_pred, average="weighted")

per_class_rows = []
for lbl in labels_order:
    pr = cls_report[lbl]["precision"]; rc = cls_report[lbl]["recall"]
    f1s = cls_report[lbl]["f1-score"]; sup = int(cls_report[lbl]["support"])
    per_class_rows.append([lbl, pr, rc, f1s, sup])

summary_rows = [
    ["Accuracy",   acc,  np.nan, np.nan, int(len(test_df))],
    ["Macro-F1",   np.nan, np.nan, f1m,  int(len(test_df))],
    ["Weighted-F1",np.nan, np.nan, f1w,  int(len(test_df))],
]

df_cls = pd.DataFrame(per_class_rows, columns=["label","precision","recall","f1","support"])
df_sum = pd.DataFrame(summary_rows,   columns=["label","precision","recall","f1","support"])

# === 6) stage1(긍/부정) 요약 ==================================================
y_true_s1 = np.array([0 if to_stage1(l)=="부정" else 1 for l in y_true_lbl])
y_pred_s1 = np.array([0 if to_stage1(id2label[p])=="부정" else 1 for p in y_pred])

p, r, f1s, sup = precision_recall_fscore_support(y_true_s1, y_pred_s1, labels=[0,1], zero_division=0)
df_stage1 = pd.DataFrame({"label":["부정","긍정"], "precision":p, "recall":r, "f1":f1s, "support":sup})
acc_s1  = accuracy_score(y_true_s1, y_pred_s1)
f1m_s1  = f1_score(y_true_s1, y_pred_s1, average="macro")

df_stage1_sum = pd.DataFrame([
    {"label":"Accuracy(2-class)", "precision":np.nan, "recall":np.nan, "f1":acc_s1, "support":int(len(test_df))},
    {"label":"Macro-F1(2-class)", "precision":np.nan, "recall":np.nan, "f1":f1m_s1, "support":int(len(test_df))}
])

# === 7) 혼동행렬(저장) ========================================================
cm = confusion_matrix(y_true, y_pred, labels=list(range(len(labels_order))))
fig, ax = plt.subplots(figsize=(6,6))
im = ax.imshow(cm, interpolation='nearest')
ax.set_title("Confusion Matrix (6-class)")
ax.set_xticks(range(len(labels_order))); ax.set_xticklabels(labels_order, rotation=45, ha="right")
ax.set_yticks(range(len(labels_order))); ax.set_yticklabels(labels_order)
for i in range(cm.shape[0]):
    for j in range(cm.shape[1]):
        ax.text(j, i, cm[i, j], ha="center", va="center",
                fontsize=9, color="white" if cm[i,j] > cm.max()/2 else "black")
plt.tight_layout()
CM_PATH = os.path.join(MODEL_DIR, "confusion_matrix.png")
plt.savefig(CM_PATH, dpi=160); plt.close()

# === 8) 저장(CSV/HTML) ========================================================
OUT_CSV_6C = os.path.join(MODEL_DIR, "eval_6class_report.csv")
OUT_CSV_2C = os.path.join(MODEL_DIR, "eval_2class_report.csv")
OUT_HTML   = os.path.join(MODEL_DIR, "eval_report.html")

pd.concat([df_cls, df_sum], ignore_index=True).to_csv(OUT_CSV_6C, index=False, encoding="utf-8-sig")
pd.concat([df_stage1, df_stage1_sum], ignore_index=True).to_csv(OUT_CSV_2C, index=False, encoding="utf-8-sig")

def style_tbl(df, title):
    df2 = df.copy()
    # 숫자 컬럼을 float로 강제 변환(문자/None → NaN)
    for col in ["precision", "recall", "f1"]:
        if col in df2.columns:
            df2[col] = pd.to_numeric(df2[col], errors="coerce")
    sty = (df2.style
           .format(formatter={"precision":"{:.3f}", "recall":"{:.3f}", "f1":"{:.3f}"},
                   na_rep="")          # ← NaN은 빈칸으로
           .set_caption(title)
           .hide(axis="index"))
    return sty.to_html()

html = f"""
<h2>Emotion Model Evaluation</h2>
<p><b>Model dir:</b> {MODEL_DIR}</p>
<p><b>Data:</b> {os.path.basename(CSV_PATH)} | <b>Test size:</b> {len(test_df)}</p>
<h3>6-class (stage2)</h3>
{style_tbl(df_cls, "Per-class metrics (stage2)")}
{style_tbl(df_sum, "Summary (stage2)")}
<h3>2-class (stage1: 긍정/부정)</h3>
{style_tbl(df_stage1, "Per-class metrics (stage1)")}
{style_tbl(df_stage1_sum, "Summary (stage1)")}
<h3>Confusion Matrix</h3>
<img src="confusion_matrix.png" width="420">
"""
with open(OUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print("✅ Saved:")
print(" -", OUT_CSV_6C)
print(" -", OUT_CSV_2C)
print(" -", OUT_HTML)
print(" -", CM_PATH)
