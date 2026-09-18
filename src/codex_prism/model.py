"""Lossless public app-server event reduction, independent of rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


def pretty(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


@dataclass
class Entry:
    id: str
    kind: str
    turn_id: str = ""
    raw: dict = field(default_factory=dict)
    text: str = ""
    command: str = ""
    cwd: str = ""
    output: str = ""
    summary: dict[int, str] = field(default_factory=dict)
    content: dict[int, str] = field(default_factory=dict)
    status: str = "inProgress"
    exit_code: int | None = None
    duration_ms: int | None = None
    revision: int = 0

    @property
    def title(self) -> str:
        if self.kind == "command":
            return self.command.splitlines()[0] if self.command else "Shell command"
        if self.kind == "tool":
            return (
                ".".join(
                    str(self.raw[k])
                    for k in ("server", "namespace", "tool", "name")
                    if self.raw.get(k)
                )
                or "Tool call"
            )
        return {
            "reasoning": "Reasoning",
            "assistant": "Answer",
            "commentary": "Commentary",
            "user": "You",
            "file": "File changes",
            "plan": "Plan",
            "system": "Session",
            "error": "Error",
            "approval": "Approval required",
        }.get(self.kind, self.kind)

    @property
    def content_text(self) -> str:
        return "\n\n".join(self.content[k] for k in sorted(self.content))

    @property
    def summary_text(self) -> str:
        return "\n\n".join(self.summary[k] for k in sorted(self.summary))

    @property
    def searchable(self) -> str:
        return "\n".join(
            (
                self.title,
                self.text,
                self.command,
                self.cwd,
                self.output,
                self.content_text,
                self.summary_text,
            )
        )

    @property
    def upstream_truncated(self) -> bool:
        return any(
            s in self.output.lower()
            for s in (
                "tokens truncated",
                "output truncated",
                "output was truncated",
                "truncated output",
            )
        )


KIND = {
    "userMessage": "user",
    "agentMessage": "assistant",
    "reasoning": "reasoning",
    "commandExecution": "command",
    "fileChange": "file",
    "mcpToolCall": "tool",
    "dynamicToolCall": "tool",
    "functionCallOutput": "tool",
    "collabAgentToolCall": "tool",
    "webSearch": "tool",
    "plan": "plan",
}


class Trace:
    def __init__(self) -> None:
        self.entries: dict[str, Entry] = {}
        self.thread_id = ""
        self.turn_id = ""
        self.status = "ready"
        self.model = ""
        self.cwd = ""
        self.usage: dict = {}
        self.serial = 0

    def add(self, kind: str, text: str, *, id: str | None = None) -> Entry:
        self.serial += 1
        entry = Entry(id or f"local-{self.serial}", kind, text=text, status="completed")
        self.entries[entry.id] = entry
        return entry

    def item(self, item: dict, turn_id: str = "", complete: bool = False) -> Entry:
        key = item.get("id") or f"anonymous-{len(self.entries)}"
        typ = item.get("type", "unknown")
        e = self.entries.get(key)
        if e is None:
            e = Entry(key, KIND.get(typ, "system"), turn_id=turn_id)
            self.entries[key] = e
        e.raw.update(item)
        e.kind = KIND.get(typ, e.kind)
        if turn_id:
            e.turn_id = turn_id
        e.status = item.get("status") or ("completed" if complete else e.status)
        if typ == "reasoning":
            # Completed snapshots may omit streamed content. Never discard it.
            for field_name in ("summary", "content"):
                parts = item.get(field_name) or []
                for index, value in enumerate(parts):
                    if value:
                        getattr(e, field_name)[index] = value
        elif typ == "commandExecution":
            e.command = item.get("command", e.command)
            e.cwd = item.get("cwd", e.cwd)
            output = item.get("aggregatedOutput")
            # The streamed output can be longer than the server's final display cap.
            if output is not None and len(output) >= len(e.output):
                e.output = output
            e.exit_code = item.get("exitCode", e.exit_code)
            e.duration_ms = item.get("durationMs", e.duration_ms)
        elif typ == "userMessage":
            e.text = "\n".join(c.get("text", pretty(c)) for c in item.get("content", []))
        elif typ in {"agentMessage", "plan"}:
            e.text = item.get("text", e.text)
            if typ == "agentMessage" and item.get("phase") == "commentary":
                e.kind = "commentary"
        elif typ == "fileChange":
            e.text = "\n\n".join(
                f"{c.get('path', '')}\n{c.get('diff', pretty(c))}" for c in item.get("changes", [])
            )
        elif e.kind == "tool":
            args = item.get("arguments")
            if args is not None:
                e.text = pretty(args)
            elif typ == "webSearch":
                e.text = pretty(item.get("action", item.get("query", "")))
            elif typ == "collabAgentToolCall":
                e.text = item.get("prompt", "")
            for field_name in (
                "result",
                "output",
                "contentItems",
                "error",
                "agentsStates",
                "results",
            ):
                if item.get(field_name) is not None:
                    e.output = pretty(item[field_name])
                    break
        else:
            e.text = pretty(item)
        e.revision += 1
        return e

    def reduce(self, message: dict) -> list[Entry]:
        method = message.get("method", "")
        p = message.get("params") or {}
        if method == "thread/started":
            thread = p.get("thread", {})
            self.thread_id = thread.get("id", self.thread_id)
            self.cwd = thread.get("cwd", self.cwd)
        elif method == "turn/started":
            self.turn_id = p["turn"]["id"]
            self.status = "working"
        elif method == "turn/completed":
            self.status = p["turn"].get("status", "completed")
            self.turn_id = ""
            if p["turn"].get("error"):
                return [self.add("error", pretty(p["turn"]["error"]))]
        elif method == "thread/tokenUsage/updated":
            self.usage = p.get("tokenUsage", {})
        elif method in {"item/started", "item/completed"}:
            return [self.item(p["item"], p.get("turnId", ""), method == "item/completed")]
        elif method in {
            "item/agentMessage/delta",
            "item/plan/delta",
            "item/reasoning/textDelta",
            "item/reasoning/summaryTextDelta",
            "item/commandExecution/outputDelta",
            "item/fileChange/outputDelta",
        }:
            key = p["itemId"]
            kind = (
                "reasoning"
                if "/reasoning/" in method
                else "command"
                if "/commandExecution/" in method
                else "file"
                if "/fileChange/" in method
                else "plan"
                if "/plan/" in method
                else "assistant"
            )
            e = self.entries.setdefault(key, Entry(key, kind, turn_id=p.get("turnId", "")))
            delta = p.get("delta", "")
            if "/reasoning/" in method:
                field_name, index_name = (
                    ("content", "contentIndex")
                    if "/textDelta" in method
                    else ("summary", "summaryIndex")
                )
                bucket = getattr(e, field_name)
                index = p.get(index_name, 0)
                bucket[index] = bucket.get(index, "") + delta
            elif "/outputDelta" in method:
                e.output += delta
            else:
                e.text += delta
            e.revision += 1
            return [e]
        elif method == "item/fileChange/patchUpdated":
            e = self.entries.get(p.get("itemId"))
            if e:
                return [self.item(e.raw | {"changes": p.get("changes", [])}, e.turn_id)]
        elif method == "turn/plan/updated":
            key = "plan-" + p.get("turnId", "")
            text = p.get("explanation") or ""
            text += "\n" + "\n".join(
                f"{'✓' if s['status'] == 'completed' else '→' if s['status'] == 'inProgress' else '·'} {s['step']}"
                for s in p.get("plan", [])
            )
            e = self.entries.setdefault(key, Entry(key, "plan"))
            e.text = text.strip()
            e.revision += 1
            return [e]
        elif method in {"warning", "configWarning", "error", "prism/error"}:
            if method == "prism/error":
                self.status = "disconnected"
            return [
                self.add(
                    "error" if "error" in method.lower() else "system",
                    p.get("message") or p.get("summary") or pretty(p),
                )
            ]
        elif method == "prism/note":
            return [self.add("system", p.get("text", ""))]
        elif method == "prism/history":
            return [
                self.item(i, t.get("id", ""), True)
                for t in p.get("turns", [])
                for i in t.get("items", [])
            ]
        elif method == "prism/session":
            for attr in ("thread_id", "model", "cwd"):
                setattr(self, attr, p.get(attr, getattr(self, attr)))
        elif method == "thread/settings/updated" and p.get("threadId") == self.thread_id:
            self.model = p.get("threadSettings", {}).get("model", self.model)
        elif method in {"item/commandExecution/terminalInteraction", "item/mcpToolCall/progress"}:
            return [self.add("system", pretty(p))]
        # Unrecognized notifications remain in the journal for protocol inspection.
        return []
