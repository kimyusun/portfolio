from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TEXT_CANDIDATES = ["text", "content", "sentence", "document", "memo", "utterance", "발화문", "문장", "내용", "일기", "메모"]
LABEL_CANDIDATES = ["label", "emotion", "stage2", "emotion_label", "감정", "라벨", "class"]
DEFAULT_ENCODINGS = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]

EMOTION_KEYWORDS = {
    "기쁨": ["기분이 좋", "행복", "기쁘", "웃음", "뿌듯", "즐거"],
    "놀람": ["놀랐", "깜짝", "당황", "뜻밖", "예상치", "갑자기"],
    "분노": ["화가", "짜증", "분노", "불쾌", "열이", "참기"],
    "불안": ["불안", "걱정", "긴장", "조마조마", "두려", "초조"],
    "상처": ["상처", "서운", "속상", "아팠", "무시", "비교"],
    "슬픔": ["슬프", "우울", "외롭", "허전", "공허", "쓸쓸"],
}

PLACE_MARKERS = ["서울", "부산", "강릉", "광화문", "강남", "카페", "공원", "해변", "도서관", "지하철", "버스", "거리", "골목"]


def read_csv(path: Path, encodings: list[str] | None = None) -> tuple[list[dict[str, str]], str]:
    for encoding in encodings or DEFAULT_ENCODINGS:
        try:
            with path.open("r", encoding=encoding, newline="") as file:
                return list(csv.DictReader(file)), encoding
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("csv", b"", 0, 1, f"could not decode with {DEFAULT_ENCODINGS}")


def detect_columns(rows: list[dict[str, str]]) -> tuple[str | None, str | None]:
    if not rows:
        return None, None
    columns = list(rows[0].keys())
    lowered = {column.lower(): column for column in columns}

    text_column = next((lowered[name] for name in TEXT_CANDIDATES if name in lowered), None)
    label_column = next((lowered[name] for name in LABEL_CANDIDATES if name in lowered), None)

    if text_column is None:
        text_column = max(columns, key=lambda column: sum(len((row.get(column) or "").strip()) for row in rows))
    if label_column is None:
        candidates = [
            column for column in columns
            if column != text_column and len({(row.get(column) or "").strip() for row in rows}) <= 30
        ]
        label_column = candidates[0] if candidates else None
    return text_column, label_column


def _quartiles(values: list[int]) -> tuple[float | None, float | None]:
    if len(values) < 4:
        return None, None
    quartiles = statistics.quantiles(values, n=4)
    return quartiles[0], quartiles[2]


def _entropy(counts: Counter[str]) -> float:
    total = sum(counts.values())
    entropy = 0.0
    for count in counts.values():
        ratio = count / total if total else 0.0
        if ratio:
            entropy -= ratio * math.log2(ratio)
    return entropy


def analyze_rows(rows: list[dict[str, str]], *, text_column: str | None = None, label_column: str | None = None) -> dict[str, Any]:
    detected_text, detected_label = detect_columns(rows)
    text_column = text_column or detected_text
    label_column = label_column or detected_label
    if text_column is None or label_column is None:
        raise ValueError("could not detect text/label columns")

    texts = [(row.get(text_column) or "").strip() for row in rows]
    labels = [(row.get(label_column) or "").strip() for row in rows]
    lengths = [len(text) for text in texts]
    label_counts = Counter(labels)
    duplicate_counts = Counter(texts)
    duplicate_extra_rows = sum(count - 1 for count in duplicate_counts.values() if count > 1)

    text_to_labels: dict[str, set[str]] = defaultdict(set)
    for text, label in zip(texts, labels):
        if text:
            text_to_labels[text].add(label)
    conflicting_texts = sum(1 for values in text_to_labels.values() if len(values) > 1)

    p25, p75 = _quartiles(lengths)
    tokens = [token for text in texts for token in re.findall(r"[가-힣A-Za-z0-9]+", text)]
    top_duplicates = [
        {"text": text, "count": count}
        for text, count in duplicate_counts.most_common(10)
        if text and count > 1
    ]

    keyword_hit_ratio = {}
    for label, keywords in EMOTION_KEYWORDS.items():
        label_texts = [text for text, current_label in zip(texts, labels) if current_label == label]
        if not label_texts:
            keyword_hit_ratio[label] = 0.0
            continue
        hits = sum(1 for text in label_texts if any(keyword in text for keyword in keywords))
        keyword_hit_ratio[label] = round(hits / len(label_texts), 4)

    stage_counts: Counter[str] = Counter()
    if rows and "stage1" in rows[0]:
        stage_counts.update((row.get("stage1") or "").strip() for row in rows)

    return {
        "rowCount": len(rows),
        "columns": list(rows[0].keys()) if rows else [],
        "textColumn": text_column,
        "labelColumn": label_column,
        "labelCounts": dict(label_counts.most_common()),
        "stageCounts": dict(stage_counts.most_common()),
        "blankText": sum(1 for text in texts if not text),
        "blankLabel": sum(1 for label in labels if not label),
        "uniqueTextCount": len(set(texts)),
        "exactDuplicateExtraRows": duplicate_extra_rows,
        "sameTextDifferentLabels": conflicting_texts,
        "labelBalanceRatio": round(min(label_counts.values()) / max(label_counts.values()), 4) if label_counts else 0.0,
        "labelEntropy": round(_entropy(label_counts), 4),
        "textLength": {
            "min": min(lengths) if lengths else 0,
            "p25": p25,
            "median": statistics.median(lengths) if lengths else 0,
            "mean": round(statistics.fmean(lengths), 2) if lengths else 0,
            "p75": p75,
            "max": max(lengths) if lengths else 0,
            "shortUnder5": sum(1 for length in lengths if length < 5),
            "longOver200": sum(1 for length in lengths if length > 200),
        },
        "tokenCount": len(tokens),
        "uniqueTokenCount": len(set(tokens)),
        "typeTokenRatio": round(len(set(tokens)) / len(tokens), 4) if tokens else 0.0,
        "topDuplicateTexts": top_duplicates,
        "labelKeywordHitRatioWithinSameLabel": keyword_hit_ratio,
        "placeMarkerRatio": round(sum(1 for text in texts if any(marker in text for marker in PLACE_MARKERS)) / len(texts), 4) if texts else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/emotion_data.csv")
    parser.add_argument("--output")
    args = parser.parse_args()

    rows, encoding = read_csv(Path(args.input))
    result = analyze_rows(rows)
    result["encoding"] = encoding

    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
