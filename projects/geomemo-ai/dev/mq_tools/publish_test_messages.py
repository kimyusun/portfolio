"""Publish sample emotion or insight messages to MQ."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import aio_pika
from dotenv import find_dotenv, load_dotenv


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INSIGHT_LOGS = ROOT / "dev" / "sample_payloads" / "insight_logs_sample.json"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


async def publish(queue: str, payload: dict) -> None:
    amqp_url = require_env("AMQP_URL")
    conn = await aio_pika.connect_robust(amqp_url)
    try:
        ch = await conn.channel()
        await ch.default_exchange.publish(
            aio_pika.Message(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=queue,
        )
    finally:
        await conn.close()


def load_logs(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        logs = json.load(f)
    if not isinstance(logs, list):
        raise SystemExit("logs file must contain a JSON array")
    return logs


if __name__ == "__main__":
    load_dotenv(find_dotenv())

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    emotion = sub.add_parser("emotion")
    emotion.add_argument("--memo-id", type=int, required=True)
    emotion.add_argument("--content", required=True)

    insight = sub.add_parser("insight")
    insight.add_argument("--user-id", type=int, required=True)
    insight.add_argument("--logs-file", type=Path, default=DEFAULT_INSIGHT_LOGS)

    args = parser.parse_args()

    if args.cmd == "emotion":
        queue = os.getenv("EMOTION_REQ_QUEUE", "emotion.req")
        payload = {"memo_id": args.memo_id, "content": args.content}
        asyncio.run(publish(queue, payload))
        print(f"[emotion] published memo_id={args.memo_id} to {queue}")
    else:
        queue = os.getenv("INSIGHT_REQ_QUEUE", "insight.req")
        logs = load_logs(args.logs_file)
        payload = {"userId": args.user_id, "logs": logs}
        asyncio.run(publish(queue, payload))
        print(f"[insight] published userId={args.user_id}, logs={len(logs)} to {queue}")
