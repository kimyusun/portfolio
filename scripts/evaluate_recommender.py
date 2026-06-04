from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ai.recommender.request_parser import parse_request
from ai.recommender.recommender import recommend_top_n


def _as_int_set(values: Iterable[Any]) -> Set[int]:
    return {int(v) for v in values}


def _ranked_place_ids(items: Sequence[Dict[str, Any]]) -> List[int]:
    return [int(item["placeId"]) for item in items]


def precision_at_k(ranked_ids: Sequence[int], relevant_ids: Set[int], k: int) -> float:
    if k <= 0:
        return 0.0
    top = ranked_ids[:k]
    if not top:
        return 0.0
    hits = sum(1 for pid in top if pid in relevant_ids)
    return hits / min(k, len(top))


def recall_at_k(ranked_ids: Sequence[int], relevant_ids: Set[int], k: int) -> float:
    if not relevant_ids or k <= 0:
        return 0.0
    top = ranked_ids[:k]
    hits = sum(1 for pid in top if pid in relevant_ids)
    return hits / len(relevant_ids)


def hit_rate_at_k(ranked_ids: Sequence[int], relevant_ids: Set[int], k: int) -> float:
    if not relevant_ids or k <= 0:
        return 0.0
    return 1.0 if any(pid in relevant_ids for pid in ranked_ids[:k]) else 0.0


def reciprocal_rank_at_k(ranked_ids: Sequence[int], relevant_ids: Set[int], k: int) -> float:
    if not relevant_ids or k <= 0:
        return 0.0
    for rank, pid in enumerate(ranked_ids[:k], start=1):
        if pid in relevant_ids:
            return 1.0 / rank
    return 0.0


def dcg_at_k(ranked_ids: Sequence[int], relevance: Dict[int, float], k: int) -> float:
    score = 0.0
    for rank, pid in enumerate(ranked_ids[:k], start=1):
        gain = relevance.get(pid, 0.0)
        if gain <= 0:
            continue
        score += (2**gain - 1) / math.log2(rank + 1)
    return score


def ndcg_at_k(ranked_ids: Sequence[int], relevance: Dict[int, float], k: int) -> float:
    if k <= 0 or not relevance:
        return 0.0
    ideal_ids = [pid for pid, _ in sorted(relevance.items(), key=lambda item: item[1], reverse=True)]
    ideal = dcg_at_k(ideal_ids, relevance, k)
    if ideal <= 0:
        return 0.0
    return dcg_at_k(ranked_ids, relevance, k) / ideal


def recommend_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    parsed = parse_request(payload)
    return recommend_top_n(
        user_id=parsed["user_id"],
        candidate_places=parsed["candidates"],
        recent_emotion_idx=parsed["recent_idx"],
        recent_emotion_score=parsed["recent_score"],
        fav_categories=parsed["fav_categories"],
        scrap_place_ids=parsed["scrap_place_ids"],
        place_positive_ratio=parsed["pos_ratio"],
        followed_positive_count=parsed["followed_pos_count"],
        top_n=max(parsed["top"], len(parsed["candidates"])),
        debug=parsed["debug"],
    )


def _case_relevance(case: Dict[str, Any]) -> Dict[int, float]:
    if "gradedRelevance" in case:
        return {int(pid): float(score) for pid, score in case["gradedRelevance"].items()}
    return {pid: 1.0 for pid in _as_int_set(case.get("relevantPlaceIds", []))}


def evaluate_case(case: Dict[str, Any], k: int = 3) -> Dict[str, Any]:
    items = recommend_from_payload(case["request"])
    ranked_ids = _ranked_place_ids(items)
    relevance = _case_relevance(case)
    relevant_ids = {pid for pid, score in relevance.items() if score > 0}

    return {
        "name": case.get("name", "unnamed"),
        "rankedPlaceIds": ranked_ids,
        "relevantPlaceIds": sorted(relevant_ids),
        "metrics": {
            f"precision@{k}": precision_at_k(ranked_ids, relevant_ids, k),
            f"recall@{k}": recall_at_k(ranked_ids, relevant_ids, k),
            f"hitRate@{k}": hit_rate_at_k(ranked_ids, relevant_ids, k),
            f"mrr@{k}": reciprocal_rank_at_k(ranked_ids, relevant_ids, k),
            f"ndcg@{k}": ndcg_at_k(ranked_ids, relevance, k),
        },
    }


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def evaluate_cases(cases: Sequence[Dict[str, Any]], k: int = 3) -> Dict[str, Any]:
    case_results = [evaluate_case(case, k=k) for case in cases]
    metric_names = sorted(case_results[0]["metrics"].keys()) if case_results else []
    aggregate = {
        name: _mean([result["metrics"][name] for result in case_results])
        for name in metric_names
    }
    return {
        "k": k,
        "caseCount": len(case_results),
        "aggregate": aggregate,
        "cases": case_results,
    }


def load_cases(path: Path) -> List[Dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate GeoMemo recommender ranking metrics on sample cases.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path("dev/sample_payloads/reco_eval_cases.json"),
        help="Path to evaluation cases JSON.",
    )
    parser.add_argument("--k", type=int, default=3, help="Ranking cutoff for @K metrics.")
    args = parser.parse_args()

    result = evaluate_cases(load_cases(args.cases), k=args.k)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
