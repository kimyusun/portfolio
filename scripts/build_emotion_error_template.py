from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List

REQUIRED_INPUT_COLUMNS = {"text", "stage2"}
OUTPUT_COLUMNS = ["text", "true_label", "pred_label", "score", "error_type", "memo"]


def read_domain_eval(path: Path) -> List[Dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = REQUIRED_INPUT_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"missing required columns: {sorted(missing)}")
        return list(reader)


def build_error_template(rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for row in rows:
        out.append({
            "text": row.get("text", ""),
            "true_label": row.get("stage2", ""),
            "pred_label": "",
            "score": "",
            "error_type": "",
            "memo": "",
        })
    return out


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build an emotion error-analysis template from a domain eval CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/sample_emotion_domain_eval.csv"),
        help="Domain evaluation CSV with text and stage2 columns.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/emotion_error_analysis_template.csv"),
        help="Output CSV path for manual prediction/error analysis.",
    )
    args = parser.parse_args()

    rows = build_error_template(read_domain_eval(args.input))
    write_csv(args.out, rows)
    print(f"saved {args.out} rows={len(rows)}")


if __name__ == "__main__":
    main()
