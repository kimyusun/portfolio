from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

DEFAULT_TARGET_LABELS = ["슬픔", "불안", "상처"]


def read_predictions(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def should_include(row: dict[str, str], target_labels: set[str], threshold: float) -> bool:
    true_label = row.get("true", "")
    pred_label = row.get("pred", "")
    try:
        score = float(row.get("score", "0"))
    except ValueError:
        score = 0.0
    is_correct = str(row.get("isCorrect", "")).lower() in {"true", "1", "yes"}
    target_related = true_label in target_labels or pred_label in target_labels
    return target_related and ((not is_correct) or score < threshold)


def build_boundary_cases(rows: list[dict[str, str]], *, target_labels: list[str], threshold: float = 0.7) -> list[dict[str, Any]]:
    targets = set(target_labels)
    selected = [row for row in rows if should_include(row, targets, threshold)]

    def sort_key(row: dict[str, str]) -> tuple[int, float, str]:
        is_correct = str(row.get("isCorrect", "")).lower() in {"true", "1", "yes"}
        try:
            score = float(row.get("score", "0"))
        except ValueError:
            score = 0.0
        return (1 if is_correct else 0, score, row.get("text", ""))

    output = []
    for row in sorted(selected, key=sort_key):
        is_correct = str(row.get("isCorrect", "")).lower() in {"true", "1", "yes"}
        output.append({
            "text": row.get("text", ""),
            "true_label": row.get("true", ""),
            "pred_label": row.get("pred", ""),
            "score": row.get("score", ""),
            "case_type": row.get("caseType", ""),
            "note": row.get("note", ""),
            "reason": "wrong_prediction" if not is_correct else "low_confidence",
            "suggested_action": "review_label_boundary",
            "review_memo": "",
        })
    return output


def write_cases(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "text",
        "true_label",
        "pred_label",
        "score",
        "case_type",
        "note",
        "reason",
        "suggested_action",
        "review_memo",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", default="reports/emotion_cleaned_test_predictions.csv")
    parser.add_argument("--out", default="data/emotion_boundary_candidates.csv")
    parser.add_argument("--target-labels", default=",".join(DEFAULT_TARGET_LABELS))
    parser.add_argument("--threshold", type=float, default=0.7)
    args = parser.parse_args()

    target_labels = [item.strip() for item in args.target_labels.split(",") if item.strip()]
    rows = read_predictions(Path(args.predictions))
    cases = build_boundary_cases(rows, target_labels=target_labels, threshold=args.threshold)
    write_cases(Path(args.out), cases)
    print(f"wrote {len(cases)} boundary cases to {args.out}")


if __name__ == "__main__":
    main()
