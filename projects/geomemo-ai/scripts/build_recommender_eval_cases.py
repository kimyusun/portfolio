from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


def _int_set(values: Iterable[Any]) -> Set[int]:
    return {int(value) for value in values or []}


def relevance_from_log(log: Dict[str, Any]) -> Dict[str, float]:
    """Build graded relevance from implicit feedback events.

    Weights are intentionally simple baseline labels:
    - detail view: weak interest
    - click: stronger interest
    - scrap: explicit positive feedback
    - memo creation: strongest downstream action
    """
    relevance: Dict[int, float] = {}

    for place_id in _int_set(log.get("detailViewedPlaceIds", [])):
        relevance[place_id] = max(relevance.get(place_id, 0.0), 0.5)
    for place_id in _int_set(log.get("clickedPlaceIds", [])):
        relevance[place_id] = max(relevance.get(place_id, 0.0), 1.0)
    for place_id in _int_set(log.get("scrappedPlaceIds", [])):
        relevance[place_id] = max(relevance.get(place_id, 0.0), 2.0)
    for place_id in _int_set(log.get("memoCreatedPlaceIds", [])):
        relevance[place_id] = max(relevance.get(place_id, 0.0), 3.0)

    shown_ids = _int_set(log.get("shownPlaceIds", []))
    if shown_ids:
        relevance = {pid: score for pid, score in relevance.items() if pid in shown_ids}

    return {str(pid): score for pid, score in sorted(relevance.items()) if score > 0}


def case_from_log(log: Dict[str, Any]) -> Dict[str, Any]:
    relevance = relevance_from_log(log)
    relevant_ids = [int(pid) for pid in relevance.keys()]

    return {
        "name": log.get("name") or str(log.get("requestId", "unnamed")),
        "description": log.get("description", "Converted from recommendation interaction log."),
        "sourceRequestId": log.get("requestId"),
        "relevantPlaceIds": relevant_ids,
        "gradedRelevance": relevance,
        "request": log["request"],
    }


def build_cases(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [case_from_log(log) for log in logs if relevance_from_log(log)]


def load_logs(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert recommendation interaction logs into eval cases.")
    parser.add_argument(
        "--logs",
        type=Path,
        default=Path("dev/sample_payloads/reco_interaction_logs_sample.json"),
        help="Path to recommendation interaction logs JSON.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output path. Prints to stdout when omitted.",
    )
    args = parser.parse_args()

    cases = build_cases(load_logs(args.logs))
    text = json.dumps(cases, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
