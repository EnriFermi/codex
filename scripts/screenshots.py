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
from codex_prism.model import Entry, Trace  # noqa: E402
from codex_prism.sessions import SessionPicker  # noqa: E402
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
    math_trace = Trace()
    math_trace.entries["math"] = Entry(
        id="math",
        kind="assistant",
        status="completed",
        text=r"""## Bochner integration

A function is **Bochner integrable** exactly when it is strongly measurable and

\[
\int_X \|f(x)\|_B\,d\mu(x)<\infty.
\]

For \(B=\mathbb{R}^2\), this is componentwise integration:

\[
\int_0^1(t,t^2)\,dt=\left(\frac12,\frac13\right).
\]

The same definition works when each \(f(x)\) is itself a function in \(L^2([0,1])\).

Source stays intact: `\frac{1}{2}` is code, while $\frac{1}{2}$ is math.
""",
    )
    app = Prism(Settings(record=False), trace=math_trace, offline=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.save_screenshot("prism-math.svg", path=str(root))

        class DemoSessions:
            async def request(self, method, params):
                return {
                    "data": [
                        {
                            "id": "synthetic-math",
                            "name": "Bochner integrals and Banach spaces",
                            "preview": "Componentwise integration and strongly measurable functions",
                            "cwd": "~/project/math-notes",
                            "updatedAt": 1789684200,
                        },
                        {
                            "id": "synthetic-prism",
                            "name": "Codex Prism: keyboard and clipboard",
                            "preview": "Fix prompt submission and add slash command suggestions",
                            "cwd": "~/project/codex-prism",
                            "updatedAt": 1789594200,
                        },
                        {
                            "id": "synthetic-api",
                            "name": "Investigate failing API tests",
                            "preview": "Find why the API tests fail and fix the response envelope",
                            "cwd": "~/project/atlas",
                            "updatedAt": 1789514200,
                        },
                    ]
                }

        await app.push_screen(SessionPicker(DemoSessions(), "~/project/math-notes", ""))
        await pilot.pause()
        app.save_screenshot("prism-resume.svg", path=str(root))
    for path in root.glob("prism*.svg"):
        path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
