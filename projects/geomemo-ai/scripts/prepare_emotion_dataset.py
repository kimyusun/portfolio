from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.audit_emotion_data import read_csv
except ModuleNotFoundError:
    from audit_emotion_data import read_csv

DEFAULT_COLUMNS = ["text", "stage1", "stage2", "persona"]


def normalized_text(text: str) -> str:
    return " ".join(text.strip().split())


def row_key(row: dict[str, str]) -> str:
    return normalized_text(row.get("text", ""))


def clean_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, Any]]:
    seen: set[str] = set()
    cleaned: list[dict[str, str]] = []
    duplicate_rows = 0
    conflicts: dict[str, set[str]] = defaultdict(set)

    for row in rows:
        text = normalized_text(row.get("text", ""))
        label = (row.get("stage2") or "").strip()
        if not text or not label:
            continue
        conflicts[text].add(label)
        if text in seen:
            duplicate_rows += 1
            continue
        seen.add(text)
        cleaned.append({
            "text": text,
            "stage1": (row.get("stage1") or "").strip(),
            "stage2": label,
            "persona": (row.get("persona") or "").strip(),
        })

    conflict_count = sum(1 for labels in conflicts.values() if len(labels) > 1)
    return cleaned, {
        "inputRows": len(rows),
        "cleanedRows": len(cleaned),
        "removedDuplicateRows": duplicate_rows,
        "sameTextDifferentLabels": conflict_count,
        "labelCounts": dict(Counter(row["stage2"] for row in cleaned).most_common()),
    }


def _hash_ratio(text: str, seed: str) -> float:
    digest = hashlib.sha256(f"{seed}:{text}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def stratified_split(
    rows: list[dict[str, str]],
    *,
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
    seed: str = "geomemo-ai",
) -> tuple[dict[str, list[dict[str, str]]], dict[str, Any]]:
    by_label: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_label[row["stage2"]].append(row)

    splits = {"train": [], "val": [], "test": []}
    split_by_label: dict[str, dict[str, int]] = {}
    for label, label_rows in sorted(by_label.items()):
        ordered = sorted(label_rows, key=lambda row: _hash_ratio(row["text"], seed))
        train_cut = round(len(ordered) * train_ratio)
        val_cut = train_cut + round(len(ordered) * val_ratio)

        splits["train"].extend(ordered[:train_cut])
        splits["val"].extend(ordered[train_cut:val_cut])
        splits["test"].extend(ordered[val_cut:])
        split_by_label[label] = {
            "train": len(ordered[:train_cut]),
            "val": len(ordered[train_cut:val_cut]),
            "test": len(ordered[val_cut:]),
        }

    for split_rows in splits.values():
        split_rows.sort(key=lambda row: _hash_ratio(row["text"], f"{seed}:final"))

    leakage = find_exact_leakage(splits)
    return splits, {
        "splitByLabel": split_by_label,
        "splitCounts": {name: len(values) for name, values in splits.items()},
        "exactLeakage": leakage,
    }


def find_exact_leakage(splits: dict[str, list[dict[str, str]]]) -> dict[str, int]:
    text_sets = {
        name: {row_key(row) for row in rows}
        for name, rows in splits.items()
    }
    return {
        "trainVal": len(text_sets["train"] & text_sets["val"]),
        "trainTest": len(text_sets["train"] & text_sets["test"]),
        "valTest": len(text_sets["val"] & text_sets["test"]),
    }


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=DEFAULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/emotion_data.csv")
    parser.add_argument("--cleaned-out", default="data/emotion_data_cleaned.csv")
    parser.add_argument("--train-out", default="data/emotion_train.csv")
    parser.add_argument("--val-out", default="data/emotion_val.csv")
    parser.add_argument("--test-out", default="data/emotion_test.csv")
    parser.add_argument("--report-out", default="reports/emotion_dataset_split.json")
    parser.add_argument("--seed", default="geomemo-ai")
    args = parser.parse_args()

    rows, encoding = read_csv(Path(args.input))
    cleaned, clean_report = clean_rows(rows)
    splits, split_report = stratified_split(cleaned, seed=args.seed)

    write_csv(Path(args.cleaned_out), cleaned)
    write_csv(Path(args.train_out), splits["train"])
    write_csv(Path(args.val_out), splits["val"])
    write_csv(Path(args.test_out), splits["test"])

    report = {
        "sourceEncoding": encoding,
        "cleaning": clean_report,
        "splits": split_report,
    }
    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
