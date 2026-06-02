from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REQUIRED_COLUMNS = {"text", "true_label", "pred_label"}


def load_error_rows(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        return list(reader)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def summarize_errors(rows: Iterable[Dict[str, str]]) -> Dict[str, object]:
    total_rows = 0
    evaluated_rows = 0
    correct = 0
    by_true: Counter[str] = Counter()
    by_pred: Counter[str] = Counter()
    confusion: Counter[Tuple[str, str]] = Counter()
    error_types: Counter[str] = Counter()
    examples_by_error: Dict[str, List[Dict[str, str]]] = defaultdict(list)

    for row in rows:
        total_rows += 1
        true_label = _clean(row.get("true_label"))
        pred_label = _clean(row.get("pred_label"))
        if not pred_label:
            continue

        evaluated_rows += 1
        by_true[true_label] += 1
        by_pred[pred_label] += 1
        confusion[(true_label, pred_label)] += 1

        if true_label == pred_label:
            correct += 1
            continue

        error_type = _clean(row.get("error_type")) or "unlabeled_error"
        error_types[error_type] += 1
        if len(examples_by_error[error_type]) < 3:
            examples_by_error[error_type].append({
                "text": _clean(row.get("text")),
                "true_label": true_label,
                "pred_label": pred_label,
                "score": _clean(row.get("score")),
                "memo": _clean(row.get("memo")),
            })

    accuracy = correct / evaluated_rows if evaluated_rows else 0.0
    return {
        "totalRows": total_rows,
        "evaluatedRows": evaluated_rows,
        "correct": correct,
        "accuracy": accuracy,
        "byTrueLabel": dict(sorted(by_true.items())),
        "byPredLabel": dict(sorted(by_pred.items())),
        "confusion": [
            {"true_label": true_label, "pred_label": pred_label, "count": count}
            for (true_label, pred_label), count in sorted(confusion.items())
        ],
        "errorTypes": dict(sorted(error_types.items())),
        "examplesByErrorType": dict(examples_by_error),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize a manual emotion error-analysis CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/emotion_error_analysis_template.csv"),
        help="CSV with text,true_label,pred_label,score,error_type,memo columns.",
    )
    args = parser.parse_args()

    summary = summarize_errors(load_error_rows(args.input))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
