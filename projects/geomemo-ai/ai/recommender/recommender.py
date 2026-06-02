from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from ai.emotion_policy import NEGATIVE_INDICES, valence_of

from .schema import Place

UNRELIABLE_EMOTION_WEIGHT_FACTOR = 0.25


@dataclass
class Weights:
    w_pos: float = 0.35
    w_emo: float = 0.25
    w_cat: float = 0.20
    w_scrap: float = 0.10
    w_social: float = 0.10


def _normalize(
    values: List[float],
    lo: float = 0.3,
    hi: float = 0.99,
    keys: Optional[List[int]] = None,
) -> List[float]:
    """Normalize raw scores into a stable display range."""
    if not values:
        return []

    vmin, vmax = min(values), max(values)
    span = vmax - vmin
    if span > 1e-9:
        return [lo + (v - vmin) / span * (hi - lo) for v in values]

    out: List[float] = []
    for i, _ in enumerate(values):
        seed = keys[i] if keys else i + 1
        jitter = ((seed % 997) / 997.0) * 1e-3
        out.append(lo + (hi - lo) * 0.5 + jitter)
    return out


def _cap01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _cat_pref_score(category: str, fav_map: Dict[str, int]) -> float:
    if not fav_map or not category:
        return 0.0
    max_count = max(fav_map.values())
    if max_count <= 0:
        return 0.0
    return fav_map.get(category, 0) / max_count


def _scrap_bonus(place_id: int, scraps: Set[int]) -> float:
    return 1.0 if place_id in scraps else 0.0


def _social_score(pid: int, followed_positive_count: Dict[int, int]) -> float:
    return _cap01(followed_positive_count.get(pid, 0) / 3.0)


def _emo_component(
    label_idx: Optional[int],
    label_conf: float,
    pos_ratio: float,
    cat_pref: float,
) -> float:
    """Return an emotion-aware score component.

    Negative recent emotions make high-positive-ratio places more important.
    Positive recent emotions lean a bit more toward the user's preferred
    category while still keeping place positivity in the signal.
    """
    if label_idx is None:
        return 0.5
    if label_idx in NEGATIVE_INDICES:
        strength = max(0.4, min(1.0, label_conf))
        return _cap01(0.5 + (pos_ratio - 0.5) * (0.6 + 0.4 * strength))
    target = _cap01(0.6 * cat_pref + 0.4 * pos_ratio)
    positive_strength = max(0.0, valence_of(label_idx))
    return _cap01(0.5 + positive_strength * (target - 0.5))


def _effective_weights(weights: Weights, recent_emotion_reliable: bool) -> Weights:
    if recent_emotion_reliable:
        return weights

    reduced_emo = weights.w_emo * UNRELIABLE_EMOTION_WEIGHT_FACTOR
    freed = weights.w_emo - reduced_emo
    return Weights(
        w_pos=weights.w_pos + freed * 0.40,
        w_emo=reduced_emo,
        w_cat=weights.w_cat + freed * 0.32,
        w_scrap=weights.w_scrap + freed * 0.14,
        w_social=weights.w_social + freed * 0.14,
    )


def recommend_top_n(
    user_id: int,
    candidate_places: List[Place],
    recent_emotion_idx: Optional[int],
    recent_emotion_score: float,
    fav_categories: Dict[str, int],
    scrap_place_ids: Set[int],
    place_positive_ratio: Dict[int, float],
    followed_positive_count: Dict[int, int],
    top_n: int = 5,
    debug: bool = False,
    weights: Weights = Weights(),
    recent_emotion_reliable: bool = True,
) -> List[Dict[str, Any]]:
    if top_n <= 0:
        return []

    effective_weights = _effective_weights(weights, recent_emotion_reliable)

    raws: List[float] = []
    keys: List[int] = []
    reasons: List[Dict[str, float]] = []

    for pl in candidate_places:
        pid = pl.placeId
        pos = _cap01(place_positive_ratio.get(pid, 0.5))
        cat = _cat_pref_score(pl.category, fav_categories)
        scr = _scrap_bonus(pid, scrap_place_ids)
        soc = _social_score(pid, followed_positive_count)
        emo = _emo_component(recent_emotion_idx, recent_emotion_score, pos, cat)

        raw = (
            effective_weights.w_pos * pos
            + effective_weights.w_emo * emo
            + effective_weights.w_cat * cat
            + effective_weights.w_scrap * scr
            + effective_weights.w_social * soc
        )

        raws.append(raw)
        keys.append(pid)

        if debug:
            reasons.append({
                "pos_ratio": round(pos, 3),
                "emo_component": round(emo, 3),
                "cat_pref": round(cat, 3),
                "scrap": round(scr, 3),
                "social": round(soc, 3),
                "emotion_reliable": 1.0 if recent_emotion_reliable else 0.0,
                "w_emo": round(effective_weights.w_emo, 3),
                "raw": round(raw, 6),
            })

    norm_scores = _normalize(raws, lo=0.3, hi=0.99, keys=keys)

    out: List[Dict[str, Any]] = []
    for i, pl in enumerate(candidate_places):
        item: Dict[str, Any] = {
            "placeId": pl.placeId,
            "name": pl.name,
            "category": pl.category,
            "latitude": pl.latitude,
            "longitude": pl.longitude,
            "score": round(norm_scores[i], 3),
        }
        if debug:
            item["reason"] = reasons[i]
        out.append(item)

    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top_n]
