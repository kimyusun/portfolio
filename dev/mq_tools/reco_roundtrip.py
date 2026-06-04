"""Publish a recommendation request and wait for its reply queue response."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

import aio_pika
from dotenv import find_dotenv, load_dotenv


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PAYLOAD = ROOT / "dev" / "sample_payloads" / "reco_req_backend.json"


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


async def main(file_path: Path, timeout_sec: int) -> None:
    load_dotenv(find_dotenv())
    amqp_url = require_env("AMQP_URL")
    req_queue = os.getenv("RECO_REQ_QUEUE", "reco.req")

    parsed = urlparse(amqp_url)
    print(f"[reco] host={parsed.hostname} vhost={parsed.path or '/'} queue={req_queue}")

    with file_path.open("r", encoding="utf-8") as f:
        payload = json.load(f)

    req_id = payload.get("requestId") or str(uuid.uuid4())
    payload["requestId"] = req_id

    conn = await aio_pika.connect_robust(amqp_url)
    try:
        ch = await conn.channel()
        reply_q_name = f"reco.reply.{uuid.uuid4().hex}"
        reply_q = await ch.declare_queue(
            reply_q_name,
            exclusive=True,
            auto_delete=True,
            durable=False,
        )

        await ch.default_exchange.publish(
            aio_pika.Message(
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                correlation_id=req_id,
                reply_to=reply_q_name,
            ),
            routing_key=req_queue,
            mandatory=True,
        )
        print(f"[reco] published requestId={req_id}; waiting on {reply_q_name}")

        async def wait_response() -> bool:
            async with reply_q.iterator() as it:
                async for msg in it:
                    async with msg.process():
                        body = json.loads(msg.body.decode("utf-8"))
                        rid = body.get("requestId") or msg.correlation_id
                        if rid == req_id:
                            print(json.dumps(body, ensure_ascii=False, indent=2))
                            return True
            return False

        ok = await asyncio.wait_for(wait_response(), timeout=timeout_sec)
        if not ok:
            print(f"[reco] no matching response within {timeout_sec}s")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", type=Path, default=DEFAULT_PAYLOAD)
    parser.add_argument("--timeout", type=int, default=20)
    args = parser.parse_args()
    asyncio.run(main(args.payload, args.timeout))
