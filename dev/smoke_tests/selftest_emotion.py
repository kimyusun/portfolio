from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def eprint(*args):
    print(*args, file=sys.stderr)


def load_label(model_dir: Path, idx: int, model) -> str:
    label_file = model_dir / "id2label.json"
    if label_file.exists():
        labels = json.loads(label_file.read_text(encoding="utf-8"))
        return labels.get(str(idx)) or labels.get(idx) or str(idx)

    id2label = getattr(model.config, "id2label", None)
    if isinstance(id2label, dict):
        return id2label.get(str(idx)) or id2label.get(idx) or str(idx)
    if isinstance(id2label, (list, tuple)) and idx < len(id2label):
        return str(id2label[idx])
    return str(idx)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, help="로컬 HuggingFace 모델 디렉터리")
    parser.add_argument("--text", default="오늘 공원 산책이 좋았어", help="추론할 문장")
    args = parser.parse_args()

    model_dir = Path(args.model_dir)
    print(f"[SELFTEST] model_dir = {model_dir}")

    if not model_dir.exists():
        eprint(f"ERROR: model dir does not exist: {model_dir}")
        sys.exit(2)

    needed = ["config.json", "tokenizer.json", "model.safetensors"]
    missing = [name for name in needed if not (model_dir / name).exists()]
    if missing:
        eprint(f"ERROR: missing model files: {missing}")
        sys.exit(3)

    try:
        import torch
        import transformers
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        print(f"[VERSIONS] torch={torch.__version__}, transformers={transformers.__version__}")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[DEVICE] using {device}")

        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True).to(device)
        model.eval()

        inputs = tokenizer(args.text, return_tensors="pt", truncation=True, max_length=256)
        inputs = {key: value.to(device) for key, value in inputs.items()}

        with torch.no_grad():
            logits = model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            idx = int(torch.argmax(probs).item())
            score = float(probs[idx].item())

        label = load_label(model_dir, idx, model)
        print("\n=== RESULT ===")
        print(f"TEXT : {args.text}")
        print(f"LABEL: {label}")
        print(f"SCORE: {score:.4f}")
        print("================")
    except Exception:
        eprint("[RUNTIME ERROR] emotion selftest failed:")
        traceback.print_exc()
        sys.exit(5)


if __name__ == "__main__":
    main()
