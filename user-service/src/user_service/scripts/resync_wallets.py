# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-generated reconciliation command that asks the credit service to open a wallet for every user.
# Author review: <to be completed by author>

"""resync-wallets: queue an OpenWallet message for every user.

For repairs, e.g. after the credit database was restored from an older backup, or a message was dead-lettered.
It's safe to run any time: the credit service ignores OpenWallet for users who already have a wallet, so nobody
is allocated credits twice. The outbox relay in the running user-service publishes the messages.
"""

import asyncio

from sqlalchemy import func, insert, literal, select

from user_service.config import Settings, get_settings
from user_service.db import create_engine
from user_service.outbox import CREDIT_COMMANDS
from user_service.tables import outbox, users


async def resync_wallets(settings: Settings) -> int:
    engine = create_engine(settings)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(
                insert(outbox).from_select(
                    ["exchange", "routing_key", "message_type", "payload"],
                    select(
                        literal(CREDIT_COMMANDS),
                        literal("wallet.open"),
                        literal("OpenWallet"),
                        func.jsonb_build_object("userId", users.c.id),
                    ).order_by(users.c.id),
                )
            )
            return result.rowcount
    finally:
        await engine.dispose()


def main() -> None:
    count = asyncio.run(resync_wallets(get_settings()))
    print(f"Queued OpenWallet for {count} users; the running user-service publishes them")


if __name__ == "__main__":
    main()
