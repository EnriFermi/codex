from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .config import DEFAULT_CONFIG, Settings, config_path
from .storage import export_markdown, private_write, replay
from .transport import AppServer


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Codex Prism · an inspectable, customizable Codex terminal client"
    )
    p.add_argument("prompt", nargs="?", help="Initial prompt")
    p.add_argument("--version", action="version", version=f"codex-prism {__version__}")
    p.add_argument(
        "--demo", action="store_true", help="Offline demo with hand-authored data; no model calls"
    )
    p.add_argument("--replay", type=Path, help="Open a Prism .jsonl[.gz] recording offline")
    p.add_argument("--cwd", "-C", default=".", help="Working directory for new Codex threads")
    p.add_argument("--codex", default="codex", help="Codex executable path")
    p.add_argument("--model", "-m", help="Model override; otherwise inherit Codex config")
    p.add_argument("--resume", metavar="THREAD_ID", help="Resume a Codex conversation")
    p.add_argument("--config", type=Path, help="Prism TOML appearance configuration")
    p.add_argument(
        "-c",
        "--codex-config",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Pass a Codex config override to the child app-server",
    )
    p.add_argument(
        "--sandbox",
        choices=["read-only", "workspace-write", "danger-full-access"],
        help="Explicit Codex sandbox override; otherwise inherited",
    )
    p.add_argument(
        "--approval",
        choices=["untrusted", "on-request", "never"],
        help="Explicit Codex approval policy override; otherwise inherited",
    )
    p.add_argument("--no-record", action="store_true", help="Disable Prism local event recordings")
    p.add_argument(
        "--init-config",
        action="store_true",
        help="Write a commented config template and exit (never overwrites)",
    )
    p.add_argument(
        "--doctor",
        action="store_true",
        help="Check executable, config, and app-server handshake; no model call",
    )
    p.add_argument(
        "--export",
        type=Path,
        metavar="FILE.md",
        help="Export --replay or --demo as Markdown and exit",
    )
    return p


async def doctor(binary: str, overrides: list[str]) -> dict:
    executable = shutil.which(binary)
    if not executable:
        raise ValueError(
            f"Codex executable not found: {binary}. Install Codex and run codex login first."
        )
    version = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, timeout=15, check=True
    ).stdout.strip()
    server = AppServer(binary, overrides, experimental_api=True)
    try:
        init = await server.start()
        return {
            "codex": version,
            "executable": executable,
            "handshake": "ok",
            "server": init.get("userAgent", "initialized"),
            "prism": __version__,
        }
    finally:
        await server.close()


def main():
    args = parser().parse_args()
    try:
        if args.init_config:
            path = args.config or config_path()
            private_write(path, DEFAULT_CONFIG)
            print(f"Created {path}\nEdit it, then press Ctrl+R in Prism.")
            return
        settings = Settings.load(args.config)
        if args.no_record:
            settings.record = False
        if args.doctor:
            print(json.dumps(asyncio.run(doctor(args.codex, args.codex_config)), indent=2))
            return
        if args.demo and args.replay:
            raise ValueError("Choose either --demo or --replay")
        trace = None
        if args.demo:
            from .demo import demo_trace

            trace = demo_trace()
        elif args.replay:
            trace = replay(args.replay)
        if args.export:
            if trace is None:
                raise ValueError("--export requires --replay or --demo")
            private_write(args.export, export_markdown(trace))
            print(args.export)
            return
        if not Path(args.cwd).expanduser().is_dir():
            raise ValueError(f"Working directory does not exist: {args.cwd}")
        if trace is None and not shutil.which(args.codex):
            raise ValueError(
                "Codex is not installed or not on PATH. Use --demo to explore Prism offline."
            )
        from .app import Prism

        Prism(
            settings,
            trace=trace,
            cwd=str(Path(args.cwd).expanduser()),
            binary=args.codex,
            model=args.model,
            resume=args.resume,
            overrides=args.codex_config,
            sandbox=args.sandbox,
            approval=args.approval,
            prompt=args.prompt,
            offline=trace is not None,
        ).run()
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError, TimeoutError) as exc:
        print(f"codex-prism: {exc}", file=sys.stderr)
        sys.exit(1)
