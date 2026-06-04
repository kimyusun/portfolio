from __future__ import annotations

import argparse
import csv
import json
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

LABELS = ["기쁨", "놀람", "분노", "불안", "상처", "슬픔"]


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


def read_cases(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    missing = {"text", "stage2"} - set(rows[0].keys() if rows else [])
    if missing:
        raise ValueError(f"missing columns: {sorted(missing)}")
    return [row for row in rows if row.get("text") and row.get("stage2")]


def precision_recall_f1(tp: int, fp: int, fn: int) -> dict[str, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def metrics_for(rows: list[dict[str, Any]], *, labels: list[str] = LABELS) -> dict[str, Any]:
    total = len(rows)
    correct = sum(1 for row in rows if row["true"] == row["pred"])
    by_label: dict[str, dict[str, float | int]] = {}

    for label in labels:
        tp = sum(1 for row in rows if row["true"] == label and row["pred"] == label)
        fp = sum(1 for row in rows if row["true"] != label and row["pred"] == label)
        fn = sum(1 for row in rows if row["true"] == label and row["pred"] != label)
        support = sum(1 for row in rows if row["true"] == label)
        label_metrics = precision_recall_f1(tp, fp, fn)
        by_label[label] = {
            "precision": round(label_metrics["precision"], 4),
            "recall": round(label_metrics["recall"], 4),
            "f1": round(label_metrics["f1"], 4),
            "support": support,
        }

    macro_f1 = sum(float(by_label[label]["f1"]) for label in labels) / len(labels)
    return {
        "caseCount": total,
        "correct": correct,
        "accuracy": round(correct / total, 4) if total else 0.0,
        "macroF1": round(macro_f1, 4),
        "byLabel": by_label,
    }


def threshold_report(rows: list[dict[str, Any]], thresholds: list[float]) -> list[dict[str, Any]]:
    total = len(rows)
    reports = []
    for threshold in thresholds:
        accepted = [row for row in rows if float(row["score"]) >= threshold]
        rejected = [row for row in rows if float(row["score"]) < threshold]
        accepted_metrics = metrics_for(accepted) if accepted else {
            "caseCount": 0,
            "correct": 0,
            "accuracy": 0.0,
            "macroF1": 0.0,
            "byLabel": {},
        }
        rejected_errors = sum(1 for row in rejected if row["true"] != row["pred"])
        reports.append({
            "threshold": threshold,
            "coverage": round(len(accepted) / total, 4) if total else 0.0,
            "accepted": len(accepted),
            "rejected": len(rejected),
            "acceptedAccuracy": accepted_metrics["accuracy"],
            "acceptedMacroF1": accepted_metrics["macroF1"],
            "rejectedErrors": rejected_errors,
            "rejectedErrorCaptureRate": round(rejected_errors / len(rejected), 4) if rejected else 0.0,
        })
    return reports


def summarize(rows: list[dict[str, Any]], thresholds: list[float]) -> dict[str, Any]:
    confusion = Counter((str(row["true"]), str(row["pred"])) for row in rows if row["true"] != row["pred"])
    low_confidence = [row for row in rows if float(row["score"]) < 0.6]
    metrics = metrics_for(rows)
    metrics.update({
        "confusion": {f"{true}->{pred}": count for (true, pred), count in confusion.items()},
        "lowConfidence": low_confidence,
        "errors": [row for row in rows if row["true"] != row["pred"]],
        "thresholds": threshold_report(rows, thresholds),
    })
    return metrics


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * percent)
    return ordered[index]


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "text",
        "true",
        "pred",
        "score",
        "isCorrect",
        "stage1",
        "persona",
        "note",
        "caseType",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in summary.items()
        if key not in {"predictions", "lowConfidence", "errors"}
    } | {
        "lowConfidenceCount": len(summary.get("lowConfidence", [])),
        "errorCount": len(summary.get("errors", [])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", default="kc_saved_model")
    parser.add_argument("--input", default="data/sample_emotion_domain_eval.csv")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--thresholds", default="0.5,0.6,0.7,0.8,0.9")
    parser.add_argument("--predictions-out")
    parser.add_argument("--errors-out")
    parser.add_argument("--summary-out")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_dir = Path(args.model_dir)
    cases = read_cases(Path(args.input))
    thresholds = [float(item.strip()) for item in args.thresholds.split(",") if item.strip()]
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir), local_files_only=True).to(device)
    model.eval()
    labels = load_labels(model_dir, model)
    load_seconds = time.perf_counter() - started

    rows: list[dict[str, Any]] = []
    inference_times: list[float] = []
    with torch.no_grad():
        for case in cases:
            infer_started = time.perf_counter()
            inputs = tokenizer(case["text"], return_tensors="pt", truncation=True, max_length=args.max_length)
            inputs = {key: value.to(device) for key, value in inputs.items()}
            logits = model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
            idx = int(torch.argmax(probs).item())
            score = float(probs[idx].item())
            inference_times.append((time.perf_counter() - infer_started) * 1000)

            pred = labels.get(idx, str(idx))
            rows.append({
                "text": case["text"],
                "true": case["stage2"],
                "pred": pred,
                "score": round(score, 4),
                "isCorrect": pred == case["stage2"],
                "stage1": case.get("stage1", ""),
                "persona": case.get("persona", ""),
                "note": case.get("note", ""),
                "caseType": case.get("case_type", ""),
            })

    summary = summarize(rows, thresholds)
    summary["device"] = str(device)
    summary["modelLoadSeconds"] = round(load_seconds, 4)
    summary["avgInferenceMs"] = round(statistics.fmean(inference_times), 4) if inference_times else 0.0
    summary["p50InferenceMs"] = round(percentile(inference_times, 0.50), 4)
    summary["p95InferenceMs"] = round(percentile(inference_times, 0.95), 4)
    summary["predictions"] = rows

    if args.predictions_out:
        write_rows(Path(args.predictions_out), rows)
    if args.errors_out:
        write_rows(Path(args.errors_out), [row for row in rows if not row["isCorrect"]])
    if args.summary_out:
        summary_path = Path(args.summary_out)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    printable = compact_summary(summary) if args.compact else summary
    print(json.dumps(printable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
