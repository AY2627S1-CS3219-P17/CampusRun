# AI Assistance Disclosure:
# Tool: Claude (claude.ai, model: Claude Opus 5.5), date: 2026-10-17
# Scope: AI-generated demo command that stands in for the Order Service: it sends credit commands over RabbitMQ
#        as the order-service user, waits for the replies and prints balances before and after.
# Author review: <to be completed by author>

"""credit-demo: drive the credit service the way the Order Service will, and watch the balances.

It connects to RabbitMQ as the order-service user, so the broker treats it exactly like the real Order Service,
and reads balances through the credit service's HTTP API with tokens it signs using JWT_SECRET.
Run it inside Compose (see the README), e.g.

    docker compose run --rm credit-demo register            # two new students; watch their wallets open
    docker compose run --rm credit-demo scenario 1 2 --pause
    docker compose run --rm credit-demo transfer --errand 41 --requester 1 --courier 2 --repeat 3
"""

import argparse
import asyncio
import json
import secrets
import time
import uuid
from typing import Any

import aio_pika
import httpx
import jwt
from aio_pika.abc import AbstractIncomingMessage
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from credit_service.broker import connect
from credit_service.commands import COMMAND_EXCHANGE, COMMANDS

REPLY_QUEUE = "order-service.credit-replies"


class DemoSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # amqp://order-service:<password>@rabbitmq:5672/ : the demo acts as the Order Service
    demo_rabbitmq_url: SecretStr
    jwt_secret: SecretStr = Field(min_length=32)
    credit_api_url: str = "http://credit-service:8000"
    user_api_url: str = "http://user-service:8000"


class OrderServiceStandIn:
    def __init__(self, settings: DemoSettings):
        self.settings = settings
        self.waiting: dict[str, asyncio.Future] = {}

    async def __aenter__(self):
        self.connection = await connect(self.settings.demo_rabbitmq_url)
        channel = await self.connection.channel(publisher_confirms=True)
        self.exchange = await channel.get_exchange(COMMAND_EXCHANGE, ensure=True)
        replies = await channel.get_queue(REPLY_QUEUE, ensure=True)
        await replies.consume(self._on_reply)
        self.http = httpx.AsyncClient(timeout=10)
        return self

    async def __aexit__(self, *exc):
        await self.http.aclose()
        await self.connection.close()

    async def _on_reply(self, message: AbstractIncomingMessage) -> None:
        async with message.process():
            future = self.waiting.pop(message.correlation_id or "", None)
            body = json.loads(message.body)
            if future is not None and not future.done():
                future.set_result(body)
            else:
                print(f"  (reply to an earlier command: errand {body.get('errandId')} is {body.get('status')})")

    async def send(self, command_type: str, body: dict[str, Any], *, wait: bool = True) -> dict | None:
        message_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        if wait:
            self.waiting[message_id] = future
        await self.exchange.publish(
            aio_pika.Message(
                json.dumps(body).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                type=command_type,
                message_id=message_id,
                # The broker refuses this unless it matches the login, so it proves who sent the command
                user_id=self.connection.url.user,
                app_id="credit-demo",
            ),
            routing_key=COMMANDS[command_type].routing_key,
        )
        if not wait:
            return None
        try:
            return await asyncio.wait_for(future, timeout=15)
        except TimeoutError:
            self.waiting.pop(message_id, None)
            print("  No reply within 15s. Is credit-worker running? The command is safe in the queue.")
            return None

    # ------------------------------------------------------------ HTTP reads

    def _token(self, user_id: int, role: str = "student") -> str:
        now = int(time.time())
        return jwt.encode(
            {"sub": str(user_id), "role": role, "iat": now, "exp": now + 300},
            self.settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        )

    async def wallet(self, user_id: int) -> dict:
        response = await self.http.get(
            f"{self.settings.credit_api_url}/wallets/me", headers={"Authorization": f"Bearer {self._token(user_id)}"}
        )
        response.raise_for_status()
        return response.json()

    async def audit(self) -> dict:
        response = await self.http.get(
            f"{self.settings.credit_api_url}/admin/audit",
            headers={"Authorization": f"Bearer {self._token(0, 'admin')}"},
        )
        response.raise_for_status()
        return response.json()

    async def show(self, label: str, user_ids: list[int], before: dict[int, dict] | None = None) -> dict[int, dict]:
        now = {u: await self.wallet(u) for u in user_ids}
        print(f"  {label}:")
        for u, w in now.items():
            if w["status"] != "ACTIVE":
                print(f"    user {u:<6} PENDING (wallet not opened yet)")
                continue
            line = f"    user {u:<6} available {w['available']:>4}   reserved {w['reserved']:>4}   total {w['total']:>4}"
            if before and before[u]["status"] == "ACTIVE":
                da = w["available"] - before[u]["available"]
                dr = w["reserved"] - before[u]["reserved"]
                if da or dr:
                    line += f"   ({da:+d} available, {dr:+d} reserved)"
                else:
                    line += "   (unchanged)"
            print(line)
        return now


def _describe(reply: dict | None) -> str:
    if reply is None:
        return "no reply"
    text = f"{reply['status']}, amount {reply['amount']}"
    if reply.get("courierId"):
        text += f", courier {reply['courierId']}"
    if reply.get("reason"):
        text += f", reason {reply['reason']}"
    if reply.get("rejection"):
        text += f"  <- not applied: {reply['rejection']}"
    return text


async def step(demo: OrderServiceStandIn, title: str, command_type: str, body: dict, users: list[int], *, repeat: int = 1, pause: bool = False):
    if pause:
        await asyncio.to_thread(input, f"\n[Enter] {title} ")
    else:
        print(f"\n{title}")
    before = await demo.show("Before", users)
    for attempt in range(repeat):
        suffix = f" (copy {attempt + 1} of {repeat})" if repeat > 1 else ""
        print(f"  -> {command_type} {json.dumps(body)}{suffix}")
        print(f"  <- {_describe(await demo.send(command_type, body))}")
    await demo.show("After", users, before)


# ------------------------------------------------------------ commands


async def scenario(demo: OrderServiceStandIn, requester: int, courier: int, pause: bool):
    users = [requester, courier]
    base = secrets.randbelow(800_000) + 100_000  # errand ids would come from the Order Service
    a, b, c = base, base + 1, base + 2
    await step(demo, f"1. Requester posts errand {a} with a 15-credit reward: credits are reserved",
               "ReserveCredits", {"errandId": a, "requesterId": requester, "amount": 15}, users, pause=pause)
    await step(demo, "2. The same reserve message is delivered twice more: nothing changes",
               "ReserveCredits", {"errandId": a, "requesterId": requester, "amount": 15}, users, repeat=2, pause=pause)
    await step(demo, "3. Requester raises the reward to 20 while the errand is OPEN",
               "AdjustReservation", {"errandId": a, "requesterId": requester, "amount": 20, "revision": 1}, users, pause=pause)
    await step(demo, f"4. Errand {a} is COMPLETED: the 20 credits move to the courier",
               "TransferCredits", {"errandId": a, "requesterId": requester, "courierId": courier}, users, pause=pause)
    await step(demo, "5. The transfer message is redelivered: the courier is not paid twice",
               "TransferCredits", {"errandId": a, "requesterId": requester, "courierId": courier}, users, pause=pause)
    await step(demo, f"6. Requester posts errand {b} for 30 credits",
               "ReserveCredits", {"errandId": b, "requesterId": requester, "amount": 30}, users, pause=pause)
    await step(demo, f"7. Errand {b} EXPIRES unaccepted: the 30 credits come back",
               "ReleaseCredits", {"errandId": b, "requesterId": requester, "reason": "EXPIRED"}, users, pause=pause)
    await step(demo, f"8. Requester tries to post errand {c} for 100 credits: not enough available",
               "ReserveCredits", {"errandId": c, "requesterId": requester, "amount": 100}, users, pause=pause)
    await show_audit(demo)


async def race(demo: OrderServiceStandIn, requester: int, count: int, amount: int):
    print(f"\nSending {count} reserves of {amount} credits for user {requester} at once")
    before = await demo.show("Before", [requester])
    base = secrets.randbelow(800_000) + 100_000
    replies = await asyncio.gather(
        *(demo.send("ReserveCredits", {"errandId": base + i, "requesterId": requester, "amount": amount}) for i in range(count))
    )
    held = sum(1 for r in replies if r and r["status"] == "HELD")
    rejected = sum(1 for r in replies if r and r["status"] == "REJECTED")
    print(f"  {held} held, {rejected} rejected (INSUFFICIENT_CREDITS), {count - held - rejected} without a reply")
    await demo.show("After", [requester], before)
    await show_audit(demo)


async def show_audit(demo: OrderServiceStandIn):
    report = await demo.audit()
    print(
        f"\nAudit: {'OK' if report['ok'] else 'PROBLEMS'} | {report['wallets']} wallets | "
        f"{report['totalAllocated']} credits allocated, {report['totalInCirculation']} in circulation "
        f"({report['totalAvailable']} available + {report['totalReserved']} reserved)"
    )
    for problem in report["problems"]:
        print(f"  ! {problem}")


async def register(demo: OrderServiceStandIn, count: int):
    """Registers students through the User Service, then watches their wallets go from PENDING to ACTIVE."""
    ids = []
    for _ in range(count):
        name = f"demo_{secrets.token_hex(3)}"
        response = await demo.http.post(
            f"{demo.settings.user_api_url}/auth/register",
            json={"email": f"{name}@u.nus.edu", "username": name, "password": "Demo-pass-123!"},
        )
        response.raise_for_status()
        ids.append(response.json()["id"])
        print(f"Registered {name} as user {ids[-1]} (password Demo-pass-123!)")
    started = time.monotonic()
    while True:
        wallets = {u: await demo.wallet(u) for u in ids}
        states = ", ".join(f"user {u}: {w['status']}" + (f" {w['available']}" if w["available"] is not None else "") for u, w in wallets.items())
        print(f"  t+{time.monotonic() - started:4.1f}s  {states}")
        if all(w["status"] == "ACTIVE" for w in wallets.values()) or time.monotonic() - started > 30:
            break
        await asyncio.sleep(0.25)


async def _main(args: argparse.Namespace) -> None:
    settings = DemoSettings()  # pyright: ignore[reportCallIssue]
    async with OrderServiceStandIn(settings) as demo:
        match args.command:
            case "register":
                await register(demo, args.count)
            case "balances":
                await demo.show("Balances", args.users)
            case "scenario":
                await scenario(demo, args.requester, args.courier, args.pause)
            case "race":
                await race(demo, args.requester, args.count, args.amount)
            case "audit":
                await show_audit(demo)
            case "reserve":
                body = {"errandId": args.errand, "requesterId": args.requester, "amount": args.amount}
                await _send(demo, "ReserveCredits", body, [args.requester], args)
            case "adjust":
                body = {"errandId": args.errand, "requesterId": args.requester, "amount": args.amount, "revision": args.revision}
                await _send(demo, "AdjustReservation", body, [args.requester], args)
            case "transfer":
                body = {"errandId": args.errand, "requesterId": args.requester, "courierId": args.courier}
                await _send(demo, "TransferCredits", body, [args.requester, args.courier], args)
            case "release":
                body = {"errandId": args.errand, "requesterId": args.requester, "reason": args.reason}
                await _send(demo, "ReleaseCredits", body, [args.requester], args)
            case "replies":
                print("Waiting 5s for replies to earlier commands...")
                await asyncio.sleep(5)


async def _send(demo: OrderServiceStandIn, command_type: str, body: dict, users: list[int], args: argparse.Namespace):
    if args.no_wait:
        for _ in range(args.repeat):
            await demo.send(command_type, body, wait=False)
        print(f"Sent {command_type} {json.dumps(body)} x{args.repeat} without waiting. It stays queued until credit-worker applies it.")
        return
    await step(demo, f"{command_type} for errand {body['errandId']}", command_type, body, users, repeat=args.repeat)


def main() -> None:
    parser = argparse.ArgumentParser(prog="credit-demo", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("register", help="register new students and watch their wallets open")
    p.add_argument("--count", type=int, default=2)
    p = sub.add_parser("balances", help="show wallets")
    p.add_argument("users", type=int, nargs="+")
    p = sub.add_parser("scenario", help="reserve, adjust, transfer, release and a refusal, step by step")
    p.add_argument("requester", type=int)
    p.add_argument("courier", type=int)
    p.add_argument("--pause", action="store_true", help="wait for Enter before each step")
    p = sub.add_parser("race", help="many reserves at once: the balance never goes negative")
    p.add_argument("requester", type=int)
    p.add_argument("--count", type=int, default=50)
    p.add_argument("--amount", type=int, default=5)
    sub.add_parser("audit", help="check the ledger, balances and conservation")
    sub.add_parser("replies", help="print replies to commands sent with --no-wait")

    def single(name: str, help_: str, *extra: tuple[str, dict]):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--errand", type=int, required=True)
        p.add_argument("--requester", type=int, required=True)
        for flag, options in extra:
            p.add_argument(flag, **options)
        p.add_argument("--repeat", type=int, default=1, help="send the same command this many times")
        p.add_argument("--no-wait", action="store_true", help="don't wait for the reply (e.g. while credit-worker is stopped)")

    single("reserve", "hold credits for an errand", ("--amount", {"type": int, "required": True}))
    single("adjust", "change an errand's held credits", ("--amount", {"type": int, "required": True}), ("--revision", {"type": int, "required": True}))
    single("transfer", "pay the held credits to the courier", ("--courier", {"type": int, "required": True}))
    single("release", "return the held credits", ("--reason", {"choices": ["CANCELLED", "EXPIRED"], "default": "CANCELLED"}))

    asyncio.run(_main(parser.parse_args()))
