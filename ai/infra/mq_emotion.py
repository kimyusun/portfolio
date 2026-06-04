from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import aio_pika
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from ai.infra.emotion_message import build_emotion_result, parse_emotion_request

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("emotion-worker")

AMQP_URL = os.getenv("AMQP_URL", "amqps://guest:guest@localhost:5671/")
EMOTION_REQ_QUEUE = os.getenv("EMOTION_REQ_QUEUE", "emotion.req")
EMOTION_PREFETCH = int(os.getenv("EMOTION_PREFETCH", "16"))
EMOTION_TTL_MS = int(os.getenv("EMOTION_TTL_MS")) if os.getenv("EMOTION_TTL_MS") else None
EMOTION_TABLE = os.getenv("EMOTION_TABLE", "EmotionEntity")

EMO_MODEL_DIR = os.getenv("EMO_MODEL_DIR")
if not EMO_MODEL_DIR:
    raise RuntimeError("Set EMO_MODEL_DIR in .env before running the emotion worker.")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL in .env before running the emotion worker.")

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
_emo_loaded = False
_emo_tok: Optional[AutoTokenizer] = None
_emo_model: Optional[AutoModelForSequenceClassification] = None
_emo_device: torch.device = torch.device("cpu")
_emo_id2label: Dict[int, str] = {}


def _queue_args(ttl_ms: Optional[int]) -> Dict[str, Any]:
    args: Dict[str, Any] = {"x-queue-type": os.getenv("MQ_QUEUE_TYPE", "quorum")}
    if ttl_ms is not None:
        args["x-message-ttl"] = ttl_ms
    return args


def _safe_tbl(name: str) -> str:
    if not name or not _VALID_TBL.match(name):
        raise ValueError(f"Invalid table name: {name!r}")
    return name


def _load_emotion_model():
    global _emo_loaded, _emo_tok, _emo_model, _emo_device, _emo_id2label
    if _emo_loaded:
        return

    model_dir = Path(EMO_MODEL_DIR)
    if not model_dir.exists():
        raise FileNotFoundError(f"EMO_MODEL_DIR not found: {model_dir}")

    _emo_device = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    torch.set_num_threads(max(1, os.cpu_count() // 2))
    log.info("[emotion] loading HF model from %s (device=%s)", model_dir, _emo_device)

    _emo_tok = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True)
    _emo_model = AutoModelForSequenceClassification.from_pretrained(
        str(model_dir),
        local_files_only=True,
    ).to(_emo_device)
    _emo_model.eval()

    label_file = model_dir / "id2label.json"
    if label_file.exists():
        loaded_labels = json.loads(label_file.read_text(encoding="utf-8"))
        _emo_id2label = {int(k): str(v) for k, v in loaded_labels.items()}
    else:
        cfg = _emo_model.config
        if isinstance(getattr(cfg, "id2label", None), dict):
            _emo_id2label = {int(k): str(v) for k, v in cfg.id2label.items()}
        elif isinstance(getattr(cfg, "id2label", None), (list, tuple)):
            _emo_id2label = {i: str(v) for i, v in enumerate(cfg.id2label)}
        else:
            _emo_id2label = {i: f"L{i}" for i in range(cfg.num_labels)}

    log.info("[emotion] model ready. labels=%s", _emo_id2label)
    _emo_loaded = True


def _infer_sync(text_str: str) -> Tuple[str, float]:
    assert _emo_tok and _emo_model
    inputs = _emo_tok(text_str, return_tensors="pt", truncation=True, max_length=256)
    with torch.no_grad():
        logits = _emo_model(**{k: v.to(_emo_device) for k, v in inputs.items()}).logits
        probs = torch.softmax(logits, dim=-1)[0]
        idx = int(torch.argmax(probs).item())
        score = float(probs[idx].item())
    return _emo_id2label.get(idx, str(idx)), score


async def analyze_emotion_text(text_str: str) -> Tuple[str, float]:
    if not _emo_loaded:
        _load_emotion_model()
    return await asyncio.to_thread(_infer_sync, text_str)


async def save_emotion(memo_id: int, label: str, score: float):
    tbl = _safe_tbl(EMOTION_TABLE)
    async with engine.begin() as conn:
        params = {"memo_id": memo_id, "label": label, "score": score}
        res = await conn.execute(
            text(f"UPDATE {tbl} SET emotion_label=:label, emotion_score=:score WHERE memo_id=:memo_id"),
            params,
        )
        if res.rowcount and res.rowcount > 0:
            return
        await conn.execute(
            text(f"INSERT INTO {tbl} (memo_id, emotion_label, emotion_score) VALUES (:memo_id, :label, :score)"),
            params,
        )


async def run_emotion_worker():
    conn = await aio_pika.connect_robust(AMQP_URL)
    ch = await conn.channel()
    await ch.set_qos(prefetch_count=EMOTION_PREFETCH)
    await ch.declare_queue(
        EMOTION_REQ_QUEUE,
        durable=True,
        robust=True,
        arguments=_queue_args(EMOTION_TTL_MS),
    )
    log.info(
        "[emotion] ready: queue=%s prefetch=%s ttl=%s",
        EMOTION_REQ_QUEUE,
        EMOTION_PREFETCH,
        EMOTION_TTL_MS,
    )

    q = await ch.get_queue(EMOTION_REQ_QUEUE)
    async with q.iterator() as it:
        async for msg in it:
            async with msg.process(ignore_processed=True):
                try:
                    payload = json.loads(msg.body.decode("utf-8"))
                    req = parse_emotion_request(payload)
                except Exception:
                    log.exception("[emotion] invalid payload: %r", msg.body)
                    await msg.reject(requeue=False)
                    continue

                try:
                    label, score = await analyze_emotion_text(req.content)
                    result = build_emotion_result(req.memo_id, label, score)
                    await save_emotion(req.memo_id, result["emotionLabel"], result["emotionScore"])
                    log.info(
                        "[emotion] saved memo_id=%s label=%s score=%.4f safe=%s reliable=%s",
                        req.memo_id,
                        result["emotionLabel"],
                        result["emotionScore"],
                        result["safeLabel"],
                        result["isReliable"],
                    )
                except Exception:
                    log.exception("[emotion] processing failed. drop message.")
                    await msg.reject(requeue=False)


def run():
    asyncio.run(run_emotion_worker())


if __name__ == "__main__":
    run()
