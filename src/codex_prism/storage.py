"""Append-only local recordings and portable replay."""

from __future__ import annotations

import gzip
import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from .model import Trace


class Journal:
    def __init__(self, directory: Path, compress: bool = True):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        self.path = directory / f"{stamp}.trace.jsonl{'.gz' if compress else ''}"
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        self._file = os.fdopen(fd, "wb")
        self._stream = gzip.GzipFile(fileobj=self._file, mode="wb") if compress else self._file
        self.closed = False

    def write(self, message: dict, direction: str = "server") -> None:
        row = {
            "format": "codex-prism/v1",
            "at": datetime.now(UTC).isoformat(),
            "direction": direction,
            "message": message,
        }
        self._stream.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
        self._stream.flush()

    def close(self):
        if not self.closed:
            self.closed = True
            self._stream.close()
            self._file.close()


def read_recording(path: Path) -> Iterator[dict]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid recording at line {number}: {exc.msg}") from exc
            if row.get("format") == "codex-prism/v1":
                if row.get("direction") == "server":
                    yield row["message"]
            elif "method" in row:
                yield row
            else:
                raise ValueError(
                    f"Unsupported recording at line {number}; expected Prism or app-server JSONL"
                )


def replay(path: Path) -> Trace:
    trace = Trace()
    for message in read_recording(path):
        trace.reduce(message)
    trace.status = "replay"
    return trace


def export_markdown(trace: Trace) -> str:
    def fence(value: str, language: str = "") -> str:
        # A command/output may itself contain Markdown fences.
        import re

        size = max([len(s) for s in re.findall(r"`+", value)] + [2]) + 1
        ticks = "`" * size
        return f"{ticks}{language}\n{value}\n{ticks}\n"

    blocks = [
        f"# Codex Prism trace\n\nThread: {trace.thread_id or 'offline'}\nModel: {trace.model or 'unknown'}\n"
    ]
    for e in trace.entries.values():
        blocks.append(f"## {e.kind.upper()} · {e.title}\n")
        if e.cwd:
            blocks.append(f"Working directory: {e.cwd}\n")
        if e.command:
            blocks.append(fence(e.command, "bash"))
        if e.content_text:
            blocks.append("### Reasoning content (as received)\n" + e.content_text)
        if e.summary_text:
            blocks.append("### Reasoning summary\n" + e.summary_text)
        if e.text:
            blocks.append(e.text)
        if e.output:
            blocks.append("### Output\n" + fence(e.output))
        if e.exit_code is not None:
            blocks.append(f"Exit: {e.exit_code}; duration: {e.duration_ms} ms\n")
    return "\n\n".join(blocks) + "\n"


def private_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)
