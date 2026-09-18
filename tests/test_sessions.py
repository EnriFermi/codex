import asyncio
from pathlib import Path

import pytest
from textual.widgets import Input, OptionList, Static

from codex_prism.app import Prism
from codex_prism.config import Settings
from codex_prism.sessions import SessionPicker
from codex_prism.widgets import Prompt


@pytest.mark.parametrize("command", ["/resume", "/sessions"])
async def test_chooser_searches_older_page_and_resumes_history(tmp_path, command):
    app = Prism(
        Settings(record=False),
        binary=str(Path(__file__).with_name("fake_server.py")),
        cwd=str(tmp_path),
    )
    async with app.run_test(size=(100, 35)) as pilot:
        async with asyncio.timeout(5):
            while not app.ready:
                await pilot.pause(0.05)
        app.query_one("#composer", Prompt).load_text(command)
        await pilot.press("enter")
        async with asyncio.timeout(5):
            while not isinstance(app.screen, SessionPicker) or app.screen.fetching:
                await pilot.pause(0.05)
        picker = app.screen
        assert len(picker.threads) == 2
        assert picker.query_one("#session-list", OptionList).option_count == 2
        picker.query_one("#session-search", Input).value = "Banach"
        await pilot.pause()
        assert picker.query_one("#session-list", OptionList).option_count == 1
        await pilot.press("enter")
        async with asyncio.timeout(5):
            while app.trace.thread_id != "saved-math" or "old-answer" not in app.cards:
                await pilot.pause(0.05)
        assert len(app.screen_stack) == 1
        assert app.trace.entries["old-answer"].text == "Saved Bochner conversation"


async def test_session_cancel_failure_retry_and_empty_search():
    class Server:
        fail = True

        async def request(self, method, params):
            if self.fail:
                raise RuntimeError("Connection interrupted")
            return {"data": [{"id": "one", "name": "Example", "cwd": "/project", "updatedAt": 1}]}

    app = Prism(Settings(record=False), offline=True)
    server = Server()
    async with app.run_test(size=(80, 24)) as pilot:
        original = app.trace
        picker = SessionPicker(server, "/project", "current")
        app.push_screen(picker)
        await pilot.pause()
        assert picker.load_error == "Connection interrupted"
        assert picker.query_one("#session-retry").display
        server.fail = False
        await pilot.click("#session-retry")
        await pilot.pause()
        assert not picker.load_error and len(picker.threads) == 1
        picker.query_one("#session-search", Input).value = "not here"
        await pilot.pause()
        assert picker.query_one("#session-resume").disabled
        assert "No matching" in str(picker.query_one("#session-count", Static).render())
        await pilot.press("escape")
        assert app.trace is original and len(app.screen_stack) == 1


async def test_failed_history_load_keeps_previous_conversation():
    class Server:
        async def request(self, method, params):
            if method == "thread/resume":
                return {"thread": {"id": "candidate", "cwd": "/other", "historyMode": "paginated"}}
            raise RuntimeError("History unavailable")

    app = Prism(Settings(record=False), offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        old_trace = app.trace
        old_trace.thread_id = "original"
        app.server = Server()
        with pytest.raises(RuntimeError, match="History unavailable"):
            await app.switch_thread("candidate")
        await app.flush_events()
        assert app.trace is old_trace and app.trace.thread_id == "original"
        app.server = None
        await pilot.pause()
