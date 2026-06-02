from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List

from ai.emotion_policy import LABELS, VALENCE_MAP

MIN_LOGS_FOR_PATTERN = 3
MIN_LOGS_FOR_PLACE_SIGNAL = 2
MIN_LOGS_FOR_STRONG_SIGNAL = 5


@dataclass(frozen=True)
class PlaceValence:
    placeCat: str
    avgValence: float
    count: int


@dataclass(frozen=True)
class InsightEvidence:
    total_logs: int
    valid_emotion_logs: int
    valid_place_logs: int
    emotion_counts: Dict[str, int]
    place_valences: List[PlaceValence]
    confidence: str
    can_make_pattern_claim: bool
    can_make_place_claim: bool
    evidence_note: str


def normalize_log_item(item: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(item)
    if "category" not in normalized and "placeCat" in normalized:
        normalized["category"] = normalized.get("placeCat")
    if "placeName" not in normalized and "name" in normalized:
        normalized["placeName"] = normalized.get("name")
    if "label" not in normalized and "emotionLabel" in normalized:
        normalized["label"] = normalized.get("emotionLabel")
    return normalized


def emotion_counts(logs: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {label: 0 for label in LABELS}
    for raw in logs:
        label = (normalize_log_item(raw).get("label") or "").strip()
        if label in counts:
            counts[label] += 1
    return counts


def place_valences(
    logs: List[Dict[str, Any]],
    top_n: int = 5,
    min_count: int = MIN_LOGS_FOR_PLACE_SIGNAL,
) -> List[PlaceValence]:
    bucket: Dict[str, List[float]] = defaultdict(list)
    for raw in logs:
        item = normalize_log_item(raw)
        category = (item.get("category") or "").strip()
        label = (item.get("label") or "").strip()
        if category and label in VALENCE_MAP:
            bucket[category].append(VALENCE_MAP[label])

    result: List[PlaceValence] = []
    for category, values in bucket.items():
        if len(values) >= min_count:
            result.append(PlaceValence(category, round(sum(values) / len(values), 3), len(values)))

    result.sort(key=lambda item: (abs(item.avgValence), item.count), reverse=True)
    return result[:top_n]


def assess_evidence(logs: List[Dict[str, Any]]) -> InsightEvidence:
    counts = emotion_counts(logs)
    valid_emotion_logs = sum(counts.values())
    vals = place_valences(logs)
    valid_place_logs = sum(item.count for item in vals)

    if valid_emotion_logs == 0:
        confidence = "none"
        note = "감정 로그가 없어 개인화된 경향을 판단하지 않았습니다."
    elif valid_emotion_logs < MIN_LOGS_FOR_PATTERN:
        confidence = "light"
        note = "기록이 적어 경향 대신 가벼운 컨디션 조언만 제공합니다."
    elif valid_emotion_logs < MIN_LOGS_FOR_STRONG_SIGNAL:
        confidence = "limited"
        note = "기록 수가 적어 제한적인 경향으로만 해석합니다."
    else:
        confidence = "normal"
        note = "기록 수가 충분해 주간 경향을 조심스럽게 요약할 수 있습니다."

    return InsightEvidence(
        total_logs=len(logs),
        valid_emotion_logs=valid_emotion_logs,
        valid_place_logs=valid_place_logs,
        emotion_counts=counts,
        place_valences=vals,
        confidence=confidence,
        can_make_pattern_claim=valid_emotion_logs >= MIN_LOGS_FOR_PATTERN,
        can_make_place_claim=bool(vals),
        evidence_note=note,
    )


def top_emotion(counts: Dict[str, int]) -> str:
    non_zero = [(label, count) for label, count in counts.items() if count > 0]
    if not non_zero:
        return ""
    return max(non_zero, key=lambda item: item[1])[0]


def build_light_advice(evidence: InsightEvidence) -> str:
    if evidence.valid_emotion_logs == 0:
        return "이번 주 기록이 아직 적어요. 오늘 기억에 남는 장소와 감정을 하나만 남겨도 다음 인사이트가 더 또렷해져요."

    emotion = top_emotion(evidence.emotion_counts)
    if not evidence.can_make_pattern_claim:
        if emotion:
            return f"아직 기록이 적어 경향을 단정하긴 어려워요. 다만 '{emotion}' 기록이 보였으니 오늘은 짧게 숨을 고르고 컨디션을 살펴보세요."
        return "아직 기록이 적어 경향을 단정하긴 어려워요. 오늘은 무리한 해석보다 짧은 휴식 하나를 챙겨보세요."

    if evidence.can_make_place_claim:
        place = evidence.place_valences[0]
        direction = "좋게" if place.avgValence > 0 else "무겁게"
        return f"이번 기록에서는 {place.placeCat}에서 감정이 {direction} 남는 편이에요. 아직 제한적 경향이니 다음 기록까지 함께 살펴볼게요."

    if emotion:
        return f"이번 기록에서는 '{emotion}' 감정이 상대적으로 자주 보였어요. 기록 수가 많진 않으니 오늘은 가볍게 리듬을 정돈해보세요."
    return "이번 기록만으로 뚜렷한 경향은 약해요. 오늘은 장소와 감정을 하나씩 더 남기며 흐름을 살펴보세요."
