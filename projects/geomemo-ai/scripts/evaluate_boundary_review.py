from __future__ import annotations

import argparse
import csv
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

try:
    from scripts.evaluate_emotion_domain_model import metrics_for
except ModuleNotFoundError:
    from evaluate_emotion_domain_model import metrics_for

NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _cell_ref_to_col(ref: str) -> int:
    letters = "".join(ch for ch in ref if ch.isalpha())
    col = 0
    for ch in letters:
        col = col * 26 + (ord(ch.upper()) - ord("A") + 1)
    return col - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    values = []
    for item in root.findall("main:si", NS):
        texts = [node.text or "" for node in item.findall(".//main:t", NS)]
        values.append("".join(texts))
    return values


def _first_sheet_path(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    first_sheet = workbook.find("main:sheets/main:sheet", NS)
    if first_sheet is None:
        raise ValueError("workbook has no sheets")
    rel_id = first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]

    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels:
        if rel.attrib.get("Id") == rel_id:
            target = rel.attrib["Target"]
            return "xl/" + target.lstrip("/")
    raise ValueError("could not resolve first worksheet")


def _cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//main:t", NS)).strip()

    value_node = cell.find("main:v", NS)
    if value_node is None or value_node.text is None:
        return ""

    raw = value_node.text
    if cell_type == "s":
        return shared_strings[int(raw)].strip()
    return raw.strip()


def read_xlsx(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as zf:
        shared = _shared_strings(zf)
        sheet_path = _first_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet_path))

    rows: list[list[str]] = []
    for row_node in root.findall(".//main:sheetData/main:row", NS):
        row_values: list[str] = []
        for cell in row_node.findall("main:c", NS):
            col_idx = _cell_ref_to_col(cell.attrib.get("r", "A1"))
            while len(row_values) <= col_idx:
                row_values.append("")
            row_values[col_idx] = _cell_value(cell, shared)
        rows.append(row_values)

    if not rows:
        return []
    headers = [header.strip() for header in rows[0]]
    records = []
    for values in rows[1:]:
        record = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            record[header] = values[idx].strip() if idx < len(values) else ""
        records.append(record)
    return records


def read_review(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".xlsx":
        return read_xlsx(path)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def effective_label(row: dict[str, str]) -> str:
    return (row.get("review_label") or row.get("true_label") or "").strip()


def normalized_row(row: dict[str, str]) -> dict[str, Any]:
    final_label = effective_label(row)
    pred_label = (row.get("pred_label") or "").strip()
    try:
        score = float(row.get("score") or 0.0)
    except ValueError:
        score = 0.0
    return {
        "text": row.get("text", ""),
        "true": final_label,
        "pred": pred_label,
        "score": score,
        "original_true": row.get("true_label", ""),
        "review_label": row.get("review_label", ""),
        "secondary_label": row.get("secondary_label", ""),
        "review_status": row.get("review_status", ""),
        "review_memo": row.get("review_memo", ""),
    }


def evaluate_review(rows: list[dict[str, str]]) -> dict[str, Any]:
    original_rows = [
        {"true": row.get("true_label", ""), "pred": row.get("pred_label", ""), "score": float(row.get("score") or 0.0)}
        for row in rows
    ]
    reviewed_rows = [normalized_row(row) for row in rows]
    corrections = [
        row for row in reviewed_rows
        if row["review_label"] and row["review_label"] != row["original_true"]
    ]
    secondary = [row for row in reviewed_rows if row["secondary_label"]]
    changed_accuracy = metrics_for(corrections)["accuracy"] if corrections else None

    original_metrics = metrics_for(original_rows)
    reviewed_metrics = metrics_for(reviewed_rows)
    present_labels = sorted({row["true"] for row in original_rows + reviewed_rows if row["true"]})

    return {
        "rowCount": len(rows),
        "reviewedLabelCount": sum(1 for row in rows if (row.get("review_label") or "").strip()),
        "correctionCount": len(corrections),
        "secondaryLabelCount": len(secondary),
        "reviewStatusCounts": dict(Counter((row.get("review_status") or "blank").strip() or "blank" for row in rows)),
        "secondaryLabelPairs": dict(Counter(
            f"{row['true']}+{row['secondary_label']}" for row in secondary
        )),
        "presentLabels": present_labels,
        "originalMetrics": original_metrics,
        "reviewedMetrics": reviewed_metrics,
        "originalPresentLabelMetrics": metrics_for(original_rows, labels=present_labels),
        "reviewedPresentLabelMetrics": metrics_for(reviewed_rows, labels=present_labels),
        "correctionSubsetAccuracy": changed_accuracy,
        "corrections": corrections,
        "secondaryLabels": secondary,
    }


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def compact_report(report: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in report.items()
        if key not in {"corrections", "secondaryLabels"}
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/emotion_boundary_review_template.xlsx")
    parser.add_argument("--report-out", default="reports/emotion_boundary_review_report.json")
    parser.add_argument("--corrections-out", default="data/emotion_label_corrections.csv")
    parser.add_argument("--secondary-out", default="data/emotion_secondary_labels.csv")
    args = parser.parse_args()

    rows = read_review(Path(args.input))
    report = evaluate_review(rows)

    report_path = Path(args.report_out)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    fields = [
        "text",
        "original_true",
        "review_label",
        "secondary_label",
        "pred",
        "score",
        "review_status",
        "review_memo",
    ]
    write_csv(Path(args.corrections_out), report["corrections"], fields)
    write_csv(Path(args.secondary_out), report["secondaryLabels"], fields)

    print(json.dumps(compact_report(report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
