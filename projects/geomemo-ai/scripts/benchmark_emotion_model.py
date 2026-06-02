from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path


SAMPLE_TEXTS = [
    "오늘 공원 산책이 좋았어",
    "회의가 계속 밀려서 마음이 불안했어",
    "생각보다 일이 잘 풀려서 놀랐어",
    "친구 말이 계속 마음에 남아서 속상했어",
    "하루 종일 기운이 없고 슬펐어",
    "예상치 못한 일 때문에 화가 났어",
]


def load_labels(model_dir: Path, model) -> dict[int, str]:
    label_file = model_dir / "id2label.json"
    if label_file.exists():
        loaded = json.loads(label_file.read_text(encoding="utf-8"))
        return {int(key): str(value) for key, value in loaded.items()}

    id2label = getattr(model.config, "id2label", None)
    if isinstance(id2label, dict):
        return {int(key): str(value) for key, value in id2label.items()}
    if isinstance(id2label, (list, tuple)):
        return {idx: str(value) for idx, value in enumerate(id2label)}
    return {idx: str(idx) for idx in range(model.config.num_labels)}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    index = min(len(sorted_values) - 1, int(round((len(sorted_values) - 1) * p)))
    return sorted_values[index]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default="kc_saved_model")
    parser.add_argument("--loops", type=int, default=20)
    parser.add_argument("--max-length", type=int, default=256)
    args = parser.parse_args()

    import torch
    import transformers
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_dir = Path(args.model_dir)
    if not model_dir.exists():
        raise FileNotFoundError(f"model dir does not exist: {model_dir}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    load_start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True).to(device)
    model.eval()
    labels = load_labels(model_dir, model)
    load_seconds = time.perf_counter() - load_start

    timings_ms: list[float] = []
    predictions = []
    with torch.no_grad():
        for i in range(args.loops):
            text = SAMPLE_TEXTS[i % len(SAMPLE_TEXTS)]
            started = time.perf_counter()
            inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=args.max_length)
            inputs = {key: value.to(device) for key, value in inputs.items()}
            logits = model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            idx = int(torch.argmax(probs).item())
            score = float(probs[idx].item())
            timings_ms.append((time.perf_counter() - started) * 1000)
            if i < len(SAMPLE_TEXTS):
                predictions.append({"text": text, "label": labels.get(idx, str(idx)), "score": round(score, 4)})

    print(json.dumps({
        "modelDir": str(model_dir),
        "device": str(device),
        "torch": torch.__version__,
        "transformers": transformers.__version__,
        "loadSeconds": round(load_seconds, 4),
        "loops": args.loops,
        "avgMs": round(statistics.mean(timings_ms), 4),
        "p50Ms": round(percentile(timings_ms, 0.50), 4),
        "p95Ms": round(percentile(timings_ms, 0.95), 4),
        "predictions": predictions,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
