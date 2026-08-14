"""A local SMTP sink for development. Never run this in production.

Why this exists: the only way to prove the real ``SmtpTransport`` works is to
let it open a real socket, speak real SMTP, and have something on the other end
accept the message. A capture transport proves the templates render; it proves
nothing about STARTTLS negotiation, authentication, or whether the transport
reports "sent" for a connection that never opened.

It listens on loopback only. That is not a default, it is the whole safety
model: the transport refuses to send in clear text to anything except loopback,
so this server can stay plaintext without weakening the rule for real hosts.

**The captured messages contain live credentials** — verification and reset
links are exactly what this is here to observe. The output file therefore
belongs outside the repository, is written with 0600 permissions, and is
deleted by the harness that started it. Nothing here logs a message body.

Usage:
    python -m scripts.dev_smtp_sink --port 1025 --out /path/outside/the/repo
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time

MAX_MESSAGE_BYTES = 1024 * 1024


class Sink:
    """Accumulates delivered messages and appends them to a JSONL file."""

    def __init__(self, path: str) -> None:
        self.path = path
        # Create with restrictive permissions before anything is written to it.
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        os.close(fd)

    def record(self, sender: str, recipients: list, data: bytes) -> None:
        record = {
            "at": time.time(),
            "from": sender,
            "to": recipients,
            "raw": data.decode("utf-8", "replace"),
        }
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")


async def handle(reader, writer, sink: Sink) -> None:
    async def say(line: str) -> None:
        writer.write((line + "\r\n").encode())
        await writer.drain()

    sender = ""
    recipients: list = []

    await say("220 localhost TradeLens dev sink")
    while True:
        raw = await reader.readline()
        if not raw:
            break
        command = raw.decode("utf-8", "replace").strip()
        upper = command.upper()

        if upper.startswith("EHLO"):
            # No STARTTLS and no AUTH advertised. The transport only reaches
            # this server over loopback, where it does not require either, and
            # advertising capabilities that are not really implemented would
            # make a passing test mean less than it appears to.
            await say("250-localhost")
            await say("250 SIZE 10485760")
        elif upper.startswith("HELO"):
            await say("250 localhost")
        elif upper.startswith("MAIL FROM"):
            sender = command[10:].strip()
            await say("250 OK")
        elif upper.startswith("RCPT TO"):
            recipients.append(command[8:].strip())
            await say("250 OK")
        elif upper == "DATA":
            await say("354 End data with <CR><LF>.<CR><LF>")
            body = bytearray()
            while True:
                line = await reader.readline()
                if not line or line in (b".\r\n", b".\n"):
                    break
                body.extend(line)
                if len(body) > MAX_MESSAGE_BYTES:
                    break
            sink.record(sender, list(recipients), bytes(body))
            recipients = []
            await say("250 OK: queued")
        elif upper == "RSET":
            sender, recipients = "", []
            await say("250 OK")
        elif upper == "QUIT":
            await say("221 Bye")
            break
        else:
            await say("250 OK")

    writer.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=1025)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    sink = Sink(args.out)
    server = await asyncio.start_server(
        lambda r, w: handle(r, w, sink), "127.0.0.1", args.port
    )
    print(f"sink listening on 127.0.0.1:{args.port}", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
