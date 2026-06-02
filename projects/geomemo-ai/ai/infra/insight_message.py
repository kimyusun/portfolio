from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ai.infra.insight_policy import normalize_log_item


@dataclass(frozen=True)
class InsightRequest:
    user_id: int
    logs: List[Dict[str, Any]]
    request_id: Optional[str] = None


def _pick(payload: Dict[str, Any], *keys: str, default=None):
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return default


def parse_insight_request(payload: Dict[str, Any]) -> InsightRequest:
    user_id = _pick(payload, "userId", "user_id")
    logs = payload.get("logs")
    request_id = _pick(payload, "requestId", "request_id")

    if user_id is None:
        raise ValueError("payload must include userId or user_id")
    if not isinstance(logs, list):
        raise ValueError("payload must include logs[]")

    return InsightRequest(
        user_id=int(user_id),
        logs=[normalize_log_item(item) for item in logs if isinstance(item, dict)],
        request_id=str(request_id) if request_id is not None else None,
    )
