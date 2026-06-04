from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class EmotionPolicy:
    index: int
    label: str
    stage1: str
    valence: float


EMOTIONS: tuple[EmotionPolicy, ...] = (
    EmotionPolicy(0, "기쁨", "긍정", 1.0),
    # AI Hub 감정 분류 계열의 "당황" 범주를 일기/메모 도메인에 맞춰
    # 사용자에게 더 자연스러운 "놀람"으로 재명명했다.
    EmotionPolicy(1, "놀람", "긍정", 0.2),
    EmotionPolicy(2, "분노", "부정", -0.9),
    EmotionPolicy(3, "불안", "부정", -0.6),
    EmotionPolicy(4, "상처", "부정", -0.7),
    EmotionPolicy(5, "슬픔", "부정", -0.8),
)

LABELS = [e.label for e in EMOTIONS]
KOR2IDX = {e.label: e.index for e in EMOTIONS}
IDX2KOR = {e.index: e.label for e in EMOTIONS}
VALENCE_MAP = {e.label: e.valence for e in EMOTIONS}
POSITIVE_LABELS = {e.label for e in EMOTIONS if e.stage1 == "긍정"}
POSITIVE_INDICES = {e.index for e in EMOTIONS if e.stage1 == "긍정"}
NEGATIVE_INDICES = {e.index for e in EMOTIONS if e.stage1 == "부정"}


def to_label_idx(value: Union[int, str]) -> int:
    if isinstance(value, int):
        return max(0, min(len(EMOTIONS) - 1, value))

    label = str(value).strip()
    if label.isdigit():
        return max(0, min(len(EMOTIONS) - 1, int(label)))
    if label not in KOR2IDX:
        raise ValueError(f"unknown emotion label: {value!r}")
    return KOR2IDX[label]


def to_label(value: Union[int, str]) -> str:
    return IDX2KOR[to_label_idx(value)]


def valence_of(value: Union[int, str]) -> float:
    return VALENCE_MAP[to_label(value)]


def stage1_of(value: Union[int, str]) -> str:
    idx = to_label_idx(value)
    return "긍정" if idx in POSITIVE_INDICES else "부정"


def is_positive(value: Union[int, str]) -> bool:
    return to_label_idx(value) in POSITIVE_INDICES
