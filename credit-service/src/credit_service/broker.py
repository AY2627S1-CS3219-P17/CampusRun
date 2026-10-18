# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-generated RabbitMQ connection helper that waits for the broker with backoff.
# Author review: <to be completed by author>

import asyncio
import logging

import aio_pika
from aio_pika.abc import AbstractRobustConnection
from pydantic import SecretStr

log = logging.getLogger(__name__)


async def connect(url: SecretStr | None) -> AbstractRobustConnection:
    """Connects to RabbitMQ, retrying until it's up.

    A robust connection also reconnects by itself later, and restores its channels and consumers, so a broker
    restart only pauses the worker.
    """
    if url is None:
        raise RuntimeError("Set RABBITMQ_URL, e.g. amqp://credit-service:<password>@127.0.0.1:5672/")
    delay = 1.0
    while True:
        try:
            return await aio_pika.connect_robust(url.get_secret_value())
        except (OSError, aio_pika.exceptions.AMQPConnectionError) as exc:
            # The URL has the password in it, so only the error type is logged
            log.warning("RabbitMQ is unreachable (%s); retrying in %.0fs", type(exc).__name__, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
