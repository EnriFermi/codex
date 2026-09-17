"""Opt-in real Codex smoke test. Records metadata and public events locally.

Usage: uv run python scripts/smoke_live.py
Consumes one small model turn. Executes a harmless printf in this repository.
"""

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path

from codex_prism.model import Trace
from codex_prism.storage import Journal
from codex_prism.transport import AppServer


async def main(binary):
    trace = Trace()
    methods = Counter()
    done = asyncio.Event()
    requests = []
    journal = Journal(Path("private/smoke-traces"))

    def incoming(message):
        journal.write(message)
        methods[message.get("method", "response")] += 1
        trace.reduce(message)
        if "id" in message and "method" in message:
            requests.append(message)
        if message.get("method") == "turn/completed":
            done.set()

    server = AppServer(binary=binary, on_message=incoming)
    try:
        await server.start()
        result = await server.request(
            "thread/start",
            {
                "cwd": str(Path.cwd()),
                "ephemeral": True,
                "sandbox": "danger-full-access",
                "approvalPolicy": "never",
            },
        )
        thread_id = result["thread"]["id"]
        await server.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [
                    {
                        "type": "text",
                        "text": "This is a terminal-client integration smoke test. Execute exactly one harmless shell command: printf 'PRISM_SMOKE_A\\nPRISM_SMOKE_B\\n'. Do not inspect or modify any files. Then reply with only PRISM_SMOKE_OK.",
                    }
                ],
            },
        )
        await asyncio.wait_for(done.wait(), 120)
        commands = [e for e in trace.entries.values() if e.kind == "command"]
        output_ok = any(
            "PRISM_SMOKE_A" in e.output and "PRISM_SMOKE_B" in e.output for e in commands
        )
        reply_ok = any(
            "PRISM_SMOKE_OK" in e.text for e in trace.entries.values() if e.kind == "assistant"
        )
        report = {
            "status": trace.status,
            "model": result["model"],
            "commands": len(commands),
            "output_ok": output_ok,
            "reply_ok": reply_ok,
            "reasoning_content_chars": sum(len(e.content_text) for e in trace.entries.values()),
            "reasoning_summary_chars": sum(len(e.summary_text) for e in trace.entries.values()),
            "server_requests": len(requests),
            "methods": dict(methods),
        }
        Path("private/live-smoke.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        if not output_ok or not reply_ok or trace.status != "completed":
            raise SystemExit(1)
    finally:
        if trace.turn_id:
            await server.request(
                "turn/interrupt", {"threadId": trace.thread_id, "turnId": trace.turn_id}
            )
        await server.close()
        journal.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex", help="Candidate executable path")
    asyncio.run(main(parser.parse_args().codex))
