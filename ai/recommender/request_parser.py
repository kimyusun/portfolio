from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set

from ai.recommender.schema import Place, to_label_idx

log = logging.getLogger("reco-parser")
UNKNOWN_LABEL = "unknown"


def safe_to_label_idx(label: Optional[str]) -> Optional[int]:
    """Convert a known emotion label to model index; ignore unknown labels."""
    if not label:
        return None
    try:
        return to_label_idx(label)
    except Exception:
        log.debug("[recentEmotion] unknown label ignored: %s", label)
        return None


def is_reliable_recent_emotion(recent: Dict[str, Any]) -> bool:
    safe_label = str(recent.get("safeLabel") or "").strip().lower()
    if safe_label == UNKNOWN_LABEL:
        return False
    if recent.get("isReliable") is False:
        return False
    return True


def _recent_label(recent: Dict[str, Any]) -> Optional[str]:
    safe_label = recent.get("safeLabel")
    if safe_label and str(safe_label).strip().lower() != UNKNOWN_LABEL:
        return str(safe_label)
    return recent.get("label") or recent.get("emotionLabel")


def _recent_score(recent: Dict[str, Any]) -> float:
    return float(recent.get("score") or recent.get("emotionScore") or 0.0)


def parse_request(payload: Dict[str, Any]):
    user_id = int(payload["userId"])
    top = int(payload.get("top", 5))
    debug = bool(payload.get("debug", False))

    candidates: List[Place] = []
    for i, p in enumerate(payload.get("candidates") or []):
        try:
            candidates.append(Place(**p))
        except Exception as e:
            log.warning("[candidate-skip] idx=%s keys=%s error=%s: %s", i, list(p.keys()), type(e).__name__, e)

    ctx = payload.get("context", {}) or {}

    recent = ctx.get("recentEmotion")
    recent_idx: Optional[int] = None
    recent_score = 0.0
    recent_reliable = True

    if isinstance(recent, dict):
        recent_reliable = is_reliable_recent_emotion(recent)
        recent_idx = safe_to_label_idx(_recent_label(recent)) if recent_reliable else None
        recent_score = _recent_score(recent) if recent_reliable else 0.0
    elif isinstance(recent, list) and recent:
        try:
            best = max(recent, key=_recent_score)
        except Exception:
            best = recent[0]
        recent_reliable = is_reliable_recent_emotion(best)
        recent_idx = safe_to_label_idx(_recent_label(best)) if recent_reliable else None
        recent_score = _recent_score(best) if recent_reliable else 0.0
    elif recent is not None:
        log.debug("[recentEmotion] unsupported type: %s", type(recent).__name__)

    fav_categories: Dict[str, int] = dict(ctx.get("favCategories") or {})
    scrap_place_ids: Set[int] = set(ctx.get("scrapPlaceIds") or [])

    pos_ratio: Dict[int, float] = {}
    followed_pos_count: Dict[int, int] = {}
    for ps in ctx.get("placeSignals") or []:
        pid = int(ps["placeId"])
        if "posRatio" in ps and ps["posRatio"] is not None:
            pos_ratio[pid] = float(ps["posRatio"])
        if "followedPositiveCount" in ps and ps["followedPositiveCount"] is not None:
            followed_pos_count[pid] = int(ps["followedPositiveCount"])

    cand_ids = {p.placeId for p in candidates}
    pos_ratio = {pid: pos_ratio.get(pid, 0.5) for pid in cand_ids}
    followed_pos_count = {pid: followed_pos_count.get(pid, 0) for pid in cand_ids}

    return {
        "user_id": user_id,
        "top": top,
        "debug": debug,
        "candidates": candidates,
        "recent_idx": recent_idx,
        "recent_score": recent_score,
        "recent_reliable": recent_reliable,
        "fav_categories": fav_categories,
        "scrap_place_ids": scrap_place_ids,
        "pos_ratio": pos_ratio,
        "followed_pos_count": followed_pos_count,
        "cand_count": len(candidates),
    }
