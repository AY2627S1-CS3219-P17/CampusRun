# AI Assistance Disclosure:
# Tool: Claude Code (model: Claude Opus 5.5), date: 2026-10-18
# Scope: AI-generated order-worker entry point, following credit-service/worker.py: connects to the database and
#        RabbitMQ, checks the reply queue is reachable, and stops cleanly on SIGTERM.
# Author review: <to be completed by author>

"""order-worker: the order service's background process.

It will run three loops (docs/order-service-plan.md, Task 9):
    1. the outbox relay, which publishes credit commands written by the API
    2. the consumer of the credit service's ReservationResult replies
    3. the sweeper, which expires errands past their deadline and resends stuck credit commands

For now it only connects and waits, so the container setup can be checked end to end.
"""

import asyncio
import logging
import signal

from sqlalchemy import text

from order_service.broker import connect
from order_service.config import Settings, get_settings
from order_service.db import create_engine

log = logging.getLogger("order_service.worker")

# Created by rabbitmq/definitions.json; this service's RabbitMQ user may read it but not create or change it
REPLY_QUEUE = "order-service.credit-replies"


async def run(settings: Settings) -> None:
    engine = create_engine(settings)
    connection = await connect(settings.rabbitmq_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        channel = await connection.channel()
        # Looked up, not declared, like credit-worker does with its own queue
        await channel.get_queue(REPLY_QUEUE, ensure=True)
        log.info("Connected to the database and RabbitMQ (%s); waiting", REPLY_QUEUE)
        await asyncio.Event().wait()
    finally:
        await connection.close()
        await engine.dispose()


async def _main() -> None:
    task = asyncio.current_task()
    assert task is not None
    loop = asyncio.get_running_loop()
    # PID 1 in a container ignores SIGTERM unless it handles it
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        await run(get_settings())
    except asyncio.CancelledError:
        log.info("Stopped")


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # aiormq logs every reconnect attempt at length; the worker's own warnings say enough
    logging.getLogger("aiormq").setLevel(logging.CRITICAL)
    logging.getLogger("aio_pika.tools").setLevel(logging.CRITICAL)
    logging.getLogger("aio_pika").setLevel(logging.WARNING)
    asyncio.run(_main())
