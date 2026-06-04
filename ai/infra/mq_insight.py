from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import aio_pika
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
import openai

from ai.infra.insight_message import parse_insight_request
from ai.infra.insight_policy import PlaceValence, assess_evidence, build_light_advice

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("insight-worker")

AMQP_URL = os.getenv("AMQP_URL", "amqps://guest:guest@localhost:5671/")
INSIGHT_REQ_QUEUE = os.getenv("INSIGHT_REQ_QUEUE", os.getenv("MQ_QUEUE", "insight.req"))
INSIGHT_PREFETCH = int(os.getenv("INSIGHT_PREFETCH", "16"))
INSIGHT_TTL_MS = int(os.getenv("INSIGHT_TTL_MS")) if os.getenv("INSIGHT_TTL_MS") else None
INSIGHT_TABLE = os.getenv("INSIGHT_TABLE", "InsightEntity")
INSIGHT_STATUS_DONE = os.getenv("INSIGHT_STATUS", "DONE")
INSIGHT_STATUS_PENDING = os.getenv("INSIGHT_STATUS_PENDING", "PENDING")
INSIGHT_PK_COL = os.getenv("INSIGHT_PK_COL", "insight_id")
INSIGHT_CREATED_AT_COL = os.getenv("INSIGHT_CREATED_AT_COL", "createdAt")

openai.api_key = os.getenv("OPENAI_API_KEY", "")
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")
SYSTEM_MSG = "사용자의 감정 기록을 조심스럽게 읽고, 근거를 과장하지 않는 한국어 코치입니다."

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL in .env before running the insight worker.")

connect_args = {}
if os.getenv("MYSQL_SSL", "0") in ("1", "true", "True"):
    connect_args["ssl"] = {}

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
    connect_args=connect_args,
)

_VALID_TBL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _queue_args(ttl_ms: Optional[int]) -> Dict[str, Any]:
    args: Dict[str, Any] = {"x-queue-type": os.getenv("MQ_QUEUE_TYPE", "quorum")}
    if ttl_ms is not None:
        args["x-message-ttl"] = ttl_ms
    return args


def _safe_tbl(name: str) -> str:
    if not name or not _VALID_TBL.match(name):
        raise ValueError(f"Invalid table name: {name!r}")
    return name


def _format_counts_for_log(counts: Dict[str, int]) -> str:
    return ", ".join([f"{key}:{value}" for key, value in counts.items()]) or "empty"


def _vals_as_json(vals: List[PlaceValence]) -> str:
    try:
        return json.dumps(
            [{"placeCat": v.placeCat, "avgValence": v.avgValence, "count": v.count} for v in vals],
            ensure_ascii=False,
        )
    except Exception:
        return str(vals)


def generate_summary(vals: List[PlaceValence], counts: Dict[str, int]) -> str:
    if not vals:
        return "이번 주는 장소별로 말할 만큼 기록이 충분하지 않아요. 오늘 기억에 남는 장소와 감정을 하나만 더 남겨보세요."
    if not openai.api_key:
        log.error(
            "[insight] OPENAI_API_KEY missing. counts=%s, vals=%s",
            _format_counts_for_log(counts),
            _vals_as_json(vals),
        )
        return ""

    emotion_msg = ", ".join([f"{key} {value}건" for key, value in counts.items() if value])
    place_msg = ", ".join([f"{p.placeCat}({p.avgValence:+.2f}, {p.count}건)" for p in vals[:3]])

    prompt = (
        "[주간 감정 집계]\n\n"
        f"장소별 평균 감정 valence\n- {place_msg}\n\n"
        f"감정 분포\n- {emotion_msg}\n\n"
        "[요청]\n"
        "1. 데이터가 보여주는 제한적인 경향만 말해 주세요.\n"
        "2. 원인처럼 단정하지 말고, '~일 수 있어요'처럼 조심스럽게 표현해 주세요.\n"
        "3. 감정 균형을 돕는 작은 행동 제안 1개를 포함해 주세요.\n"
        "4. 150자 이내, 한국어 한 문단으로 답해 주세요."
    )

    log.debug("[insight] prompt preview: %s", prompt.replace("\n", " ")[:300])
    last_err = None
    for attempt in range(1, 3):
        try:
            model_name = os.getenv("GPT_MODEL", GPT_MODEL)
            params: Dict[str, Any] = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": SYSTEM_MSG},
                    {"role": "user", "content": prompt},
                ],
                "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.6")),
                "top_p": 1.0,
            }

            max_tok = int(os.getenv("OPENAI_MAX_TOKENS", "300"))
            if any(name in model_name for name in ["gpt-5", "o4-mini", "4o-mini"]):
                params["max_completion_tokens"] = max_tok
            else:
                params["max_tokens"] = max_tok

            try:
                chat = openai.chat.completions.create(**params)
            except openai.BadRequestError as exc:
                if "max_tokens" in str(exc) and "max_completion_tokens" in str(exc):
                    params.pop("max_tokens", None)
                    params["max_completion_tokens"] = max_tok
                    chat = openai.chat.completions.create(**params)
                else:
                    raise

            out = (chat.choices[0].message.content or "").strip().replace("\n", " ")[:150]
            if out:
                log.info("[insight] GPT summary OK (len=%s): %s", len(out), out)
                return out
            log.warning(
                "[insight] empty summary from GPT (attempt=%s). counts=%s, vals=%s",
                attempt,
                _format_counts_for_log(counts),
                _vals_as_json(vals),
            )
        except Exception as exc:
            last_err = exc
            log.exception("[insight] GPT call failed (attempt=%s)", attempt)

    log.error(
        "[insight] GPT failed after retries. counts=%s, vals=%s, error=%s",
        _format_counts_for_log(counts),
        _vals_as_json(vals),
        repr(last_err),
    )
    return ""


async def insight_update_pending_only(user_id: int, content: str) -> Optional[int]:
    tbl = _safe_tbl(INSIGHT_TABLE)
    pkcol = _safe_tbl(INSIGHT_PK_COL)
    created_col = _safe_tbl(INSIGHT_CREATED_AT_COL)

    async with engine.begin() as conn:
        try:
            rs = await conn.execute(
                text(
                    f"SELECT {pkcol} FROM {tbl} "
                    f"WHERE user_id=:uid AND status=:status "
                    f"ORDER BY {created_col} DESC LIMIT 1"
                ),
                {"uid": user_id, "status": INSIGHT_STATUS_PENDING},
            )
            row = rs.first()
        except Exception:
            log.exception("[insight] SELECT pending failed")
            return None

        if row and row[0] is not None:
            insight_id = int(row[0])
            await conn.execute(
                text(f"UPDATE {tbl} SET content=:content, status=:status WHERE {pkcol}=:insight_id"),
                {"content": content, "status": INSIGHT_STATUS_DONE, "insight_id": insight_id},
            )
            log.info("[insight] PENDING->DONE updated (insight_id=%s, user_id=%s)", insight_id, user_id)
            return insight_id

        log.warning("[insight] no PENDING row to update (user_id=%s). skipping persist", user_id)
        return None


async def run_insight_worker():
    conn = await aio_pika.connect_robust(AMQP_URL)
    ch = await conn.channel()
    await ch.set_qos(prefetch_count=INSIGHT_PREFETCH)
    await ch.declare_queue(
        INSIGHT_REQ_QUEUE,
        durable=True,
        robust=True,
        arguments=_queue_args(INSIGHT_TTL_MS),
    )
    log.info(
        "[insight] ready: queue=%s prefetch=%s ttl=%s",
        INSIGHT_REQ_QUEUE,
        INSIGHT_PREFETCH,
        INSIGHT_TTL_MS,
    )

    q = await ch.get_queue(INSIGHT_REQ_QUEUE)
    async with q.iterator() as it:
        async for msg in it:
            async with msg.process(ignore_processed=True):
                try:
                    log.debug("[insight] payload preview: %s", msg.body[:500])
                    payload = json.loads(msg.body.decode("utf-8"))
                    req = parse_insight_request(payload)
                    evidence = assess_evidence(req.logs)
                    counts = evidence.emotion_counts
                    vals = evidence.place_valences

                    log.info(
                        "[insight] logs=%s confidence=%s valid=%s placeSignals=%s note=%s",
                        len(req.logs),
                        evidence.confidence,
                        evidence.valid_emotion_logs,
                        len(vals),
                        evidence.evidence_note,
                    )

                    if evidence.can_make_pattern_claim and evidence.can_make_place_claim:
                        summary = generate_summary(vals, counts)
                    else:
                        summary = build_light_advice(evidence)

                    if not summary.strip():
                        log.warning(
                            "[insight] summary empty -> using light advice. counts=%s, vals=%s",
                            _format_counts_for_log(counts),
                            _vals_as_json(vals),
                        )
                        summary = build_light_advice(evidence)

                    insight_id = await insight_update_pending_only(req.user_id, summary)
                    if insight_id is not None:
                        log.info("[insight] done persisted for user_id=%s entries=%s", req.user_id, len(req.logs))
                    else:
                        log.warning("[insight] skipped persist for user_id=%s entries=%s", req.user_id, len(req.logs))
                except Exception:
                    log.exception("[insight] processing failed.")
                    await msg.reject(requeue=False)


def run():
    asyncio.run(run_insight_worker())


if __name__ == "__main__":
    run()
