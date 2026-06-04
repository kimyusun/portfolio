from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ai.emotion_policy import stage1_of, valence_of

DEFAULT_MIN_CONFIDENCE = 0.6
UNKNOWN_LABEL = "unknown"


@dataclass(frozen=True)
class EmotionRequest:
    memo_id: int
    content: str
    request_id: Optional[str] = None


def _pick(payload: Dict[str, Any], *keys: str, default=None):
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def parse_emotion_request(payload: Dict[str, Any]) -> EmotionRequest:
    memo_id = _pick(payload, "memo_id", "memoId", "id")
    content = _pick(payload, "content", "text", "body")
    request_id = _pick(payload, "requestId", "request_id")

    if memo_id is None:
        raise ValueError("payload must include memo_id, memoId, or id")
    if content is None or not str(content).strip():
        raise ValueError("payload must include non-empty content, text, or body")

    return EmotionRequest(
        memo_id=int(memo_id),
        content=str(content).strip(),
        request_id=str(request_id) if request_id is not None else None,
    )


def is_reliable_prediction(score: float, threshold: float = DEFAULT_MIN_CONFIDENCE) -> bool:
    return float(score) >= float(threshold)


def build_emotion_result(
    memo_id: int,
    label: str,
    score: float,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> Dict[str, Any]:
    reliable = is_reliable_prediction(score, min_confidence)
    return {
        "memoId": int(memo_id),
        "emotionLabel": label,
        "emotionScore": round(float(score), 6),
        "stage1": stage1_of(label),
        "valence": valence_of(label),
        "safeLabel": label if reliable else UNKNOWN_LABEL,
        "isReliable": reliable,
        "confidenceThreshold": float(min_confidence),
    }


def inspect_model_dir(model_dir: str | Path) -> Dict[str, Any]:
    path = Path(model_dir)
    files = {p.name for p in path.iterdir()} if path.exists() else set()

    has_model_weight = bool({"model.safetensors", "pytorch_model.bin"} & files)
    has_tokenizer = "tokenizer.json" in files or "vocab.txt" in files
    required_missing = []
    if "config.json" not in files:
        required_missing.append("config.json")
    if not has_tokenizer:
        required_missing.append("tokenizer.json or vocab.txt")
    if not has_model_weight:
        required_missing.append("model.safetensors or pytorch_model.bin")

    return {
        "path": str(path),
        "exists": path.exists(),
        "hasConfig": "config.json" in files,
        "hasTokenizer": has_tokenizer,
        "hasModelWeight": has_model_weight,
        "missing": required_missing,
        "ready": path.exists() and not required_missing,
    }
