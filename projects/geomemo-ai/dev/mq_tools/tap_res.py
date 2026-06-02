"""Print messages consumed from the recommendation response queue."""

from __future__ import annotations

import asyncio
import json
import os

import aio_pika
from dotenv import find_dotenv, load_dotenv


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


async def main() -> None:
    load_dotenv(find_dotenv())
    amqp_url = require_env("AMQP_URL")
    res_queue = os.getenv("RECO_RES_QUEUE", "reco.res")

    conn = await aio_pika.connect_robust(amqp_url)
    try:
        ch = await conn.channel()
        q = await ch.get_queue(res_queue)
        print(f"[tap] listening on {res_queue}; press Ctrl+C to stop")

        async with q.iterator() as it:
            async for msg in it:
                async with msg.process():
                    try:
                        body = json.loads(msg.body.decode("utf-8"))
                        print(json.dumps(body, ensure_ascii=False, indent=2))
                    except Exception:
                        print(msg.body.decode("utf-8", "ignore"))
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
