#!/usr/bin/env python3
"""Controlled JSON-RPC peer used only by transport tests."""

import json
import sys

settings = {}


def send(value):
    print(json.dumps(value), flush=True)


for line in sys.stdin:
    m = json.loads(line)
    method = m.get("method")
    if method == "initialize":
        send({"id": m["id"], "result": {"userAgent": "fake/1"}})
    elif method == "thread/start":
        thread = {"id": "test-thread", "cwd": m["params"].get("cwd", "/tmp"), "turns": []}
        settings = {
            "model": "test-model",
            "effort": "medium",
            "cwd": thread["cwd"],
            "approvalPolicy": "on-request",
            "approvalsReviewer": "user",
            "activePermissionProfile": {"id": ":read-only"},
            "sandboxPolicy": {"type": "readOnly"},
        }
        send(
            {
                "id": m["id"],
                "result": {
                    "thread": thread,
                    "model": "test-model",
                    "cwd": thread["cwd"],
                    "approvalPolicy": "on-request",
                    "sandbox": {"type": "readOnly"},
                    "approvalsReviewer": "user",
                    "activePermissionProfile": {"id": ":read-only"},
                    "reasoningEffort": "medium",
                },
            }
        )
        send({"method": "thread/started", "params": {"thread": thread}})
    elif method == "model/list":
        send(
            {
                "id": m["id"],
                "result": {
                    "data": [
                        {
                            "id": "test-model",
                            "model": "test-model",
                            "displayName": "Test model",
                            "description": "A model for UI tests",
                            "defaultReasoningEffort": "medium",
                            "supportedReasoningEfforts": [
                                {"reasoningEffort": "medium", "description": "Balanced"},
                                {"reasoningEffort": "high", "description": "More reasoning"},
                            ],
                        }
                    ],
                    "nextCursor": None,
                },
            }
        )
    elif method == "thread/settings/update":
        changes = dict(m["params"])
        changes.pop("threadId")
        if profile := changes.pop("permissions", None):
            changes["activePermissionProfile"] = {"id": profile}
            changes["sandboxPolicy"] = {
                "type": {
                    ":read-only": "readOnly",
                    ":workspace": "workspaceWrite",
                    ":danger-full-access": "dangerFullAccess",
                }[profile]
            }
        settings.update(changes)
        send({"id": m["id"], "result": {}})
        send(
            {
                "method": "thread/settings/updated",
                "params": {"threadId": "test-thread", "threadSettings": settings},
            }
        )
    elif method == "thread/list":
        older = bool(m["params"].get("cursor"))
        send(
            {
                "id": m["id"],
                "result": {
                    "data": [
                        {
                            "id": "saved-math" if older else "saved-ui",
                            "name": "Bochner integrals" if older else "UI input fixes",
                            "preview": "Integration in Banach spaces"
                            if older
                            else "Keyboard and clipboard",
                            "cwd": "/math" if older else "/ui",
                            "updatedAt": 1789600000,
                        }
                    ],
                    "nextCursor": None if older else "older-page",
                },
            }
        )
    elif method == "thread/resume":
        send(
            {
                "id": m["id"],
                "result": {
                    "thread": {
                        "id": m["params"]["threadId"],
                        "cwd": "/math",
                        "historyMode": "paginated",
                    },
                    "model": "test-model",
                    "cwd": "/math",
                },
            }
        )
    elif method == "thread/turns/list":
        send(
            {
                "id": m["id"],
                "result": {
                    "data": [
                        {
                            "id": "old-turn",
                            "status": "completed",
                            "items": [
                                {
                                    "id": "old-answer",
                                    "type": "agentMessage",
                                    "text": "Saved Bochner conversation",
                                    "phase": "final_answer",
                                }
                            ],
                        }
                    ],
                    "nextCursor": None,
                },
            }
        )
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
    elif method == "turn/interrupt":
        send({"id": m["id"], "result": {}})
        send(
            {
                "method": "turn/completed",
                "params": {"turn": {"id": m["params"]["turnId"], "status": "interrupted"}},
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
