"""Render synthetic demo screenshots to SVG; no Codex/model calls."""

import asyncio
import os
from pathlib import Path

os.environ.pop("NO_COLOR", None)
os.environ["TERM"] = "xterm-256color"
os.environ["COLORTERM"] = "truecolor"

from codex_prism.app import Prism  # noqa: E402
from codex_prism.config import Settings  # noqa: E402
from codex_prism.demo import demo_trace  # noqa: E402
from codex_prism.widgets import Prompt  # noqa: E402


async def main():
    root = Path(__file__).resolve().parents[1] / "docs"
    app = Prism(Settings(), trace=demo_trace(), offline=True)
    async with app.run_test(size=(132, 48)) as pilot:
        await pilot.pause()
        app.save_screenshot("prism.svg", path=str(root))
        app.select_entry("demo-search")
        await pilot.pause()
        app.save_screenshot("prism-command.svg", path=str(root))
        app.select_entry("demo-tests")
        app.action_toggle_output()
        await pilot.pause()
        app.save_screenshot("prism-output.svg", path=str(root))
        app.select_entry("demo-search")
        app.action_focus_input()
        app.query_one("#composer", Prompt).load_text("/")
        await pilot.pause()
        app.save_screenshot("prism-commands.svg", path=str(root))
    for path in root.glob("prism*.svg"):
        path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
