#!/usr/bin/env python3
"""Controlled JSON-RPC peer used only by transport tests."""

import json
import sys


def send(value):
    print(json.dumps(value), flush=True)


for line in sys.stdin:
    m = json.loads(line)
    method = m.get("method")
    if method == "initialize":
        send({"id": m["id"], "result": {"userAgent": "fake/1"}})
    elif method == "thread/start":
        thread = {"id": "test-thread", "cwd": m["params"].get("cwd", "/tmp"), "turns": []}
        send(
            {
                "id": m["id"],
                "result": {
                    "thread": thread,
                    "model": "test-model",
                    "cwd": thread["cwd"],
                    "approvalPolicy": "on-request",
                    "sandbox": {"type": "readOnly"},
                },
            }
        )
        send({"method": "thread/started", "params": {"thread": thread}})
    elif method == "turn/start":
        send({"id": m["id"], "result": {"turn": {"id": "test-turn", "status": "inProgress"}}})
        send({"method": "turn/started", "params": {"turn": {"id": "test-turn"}}})
        send(
            {
                "method": "item/completed",
                "params": {
                    "item": {"type": "userMessage", "id": "u", "content": m["params"]["input"]}
                },
            }
        )
        send(
            {
                "method": "item/started",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "id": "c",
                        "command": "printf 'hello\\n'",
                        "cwd": "/tmp",
                    }
                },
            }
        )
        send(
            {
                "method": "item/commandExecution/outputDelta",
                "params": {"itemId": "c", "delta": "hello\n"},
            }
        )
        send(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "id": "c",
                        "command": "printf 'hello\\n'",
                        "aggregatedOutput": "hello\n",
                        "exitCode": 0,
                        "durationMs": 10,
                    }
                },
            }
        )
        send(
            {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "agentMessage",
                        "id": "a",
                        "text": "Test complete.",
                        "phase": "final_answer",
                    }
                },
            }
        )
        send(
            {
                "method": "turn/completed",
                "params": {"turn": {"id": "test-turn", "status": "completed"}},
            }
        )
    elif method == "test/big":
        send(
            {
                "method": "item/commandExecution/outputDelta",
                "params": {"itemId": "big", "delta": "x" * 300000},
            }
        )
        send({"id": m["id"], "result": {"ok": True}})
    elif method == "test/error":
        send({"id": m["id"], "error": {"code": -32000, "message": "deliberate error"}})
    elif method == "test/approval":
        send(
            {
                "id": "server-approval",
                "method": "item/commandExecution/requestApproval",
                "params": {"command": "echo test"},
            }
        )
        send({"id": m["id"], "result": {"ok": True}})
    elif method == "test/eof":
        break
    elif method == "test/timeout":
        continue
    elif method == "test/echo":
        send({"id": m["id"], "result": m["params"]})
