import asyncio
from pathlib import Path

import pytest

from codex_prism.app import Prism
from codex_prism.commands import COMMANDS
from codex_prism.config import Settings
from codex_prism.sessions import SessionPicker
from codex_prism.widgets import DetailScreen, Prompt


@pytest.mark.parametrize("command", [c.text.strip() for c in COMMANDS])
async def test_every_advertised_command_from_composer(tmp_path, command, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    app = Prism(
        Settings(record=False),
        binary=str(Path(__file__).with_name("fake_server.py")),
        cwd=str(tmp_path),
    )
    async with app.run_test(size=(80, 24)) as pilot:
        async with asyncio.timeout(5):
            while not app.ready:
                await pilot.pause(0.05)
        original = app.trace
        calls = []
        original_request = app.server.request

        async def request(method, params, **kwargs):
            calls.append(method)
            return await original_request(method, params, **kwargs)

        app.server.request = request
        if command == "/stop":
            app.trace.turn_id = "running-turn"
        text = "/theme ember" if command == "/theme" else command
        prompt = app.query_one("#composer", Prompt)
        prompt.load_text(text)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        async with asyncio.timeout(5):
            while app.switching:
                await pilot.pause(0.05)
        if command in {"/quit", "/exit"}:
            async with asyncio.timeout(5):
                while not app._exit:
                    await asyncio.sleep(0.01)
        elif command == "/help":
            assert isinstance(app.screen, DetailScreen)
            await pilot.press("escape")
        elif command in {"/resume", "/sessions"}:
            assert isinstance(app.screen, SessionPicker)
            async with asyncio.timeout(5):
                while app.screen.fetching:
                    await pilot.pause(0.05)
            assert len(app.screen.threads) == 2
            await pilot.press("escape")
        elif command == "/new":
            assert app.trace is not original and "thread/start" in calls
        elif command == "/theme":
            assert app.settings.theme == "ember"
        elif command == "/export":
            assert list(tmp_path.glob("codex-prism/exports/*.md"))
        elif command == "/stop":
            assert "turn/interrupt" in calls
        assert "turn/start" not in calls
        if not app._exit:
            assert prompt.text == ""
    assert app.server.process.returncode is not None


@pytest.mark.parametrize("command", ["/help", "/theme ember", "/quit", "/exit"])
async def test_local_commands_work_while_busy_or_disconnected(command):
    app = Prism(Settings(record=False), offline=True)
    async with app.run_test(size=(80, 24)) as pilot:
        app.ready = False
        app.sending = True
        app.switching = True
        await pilot.press("i")
        app.query_one("#composer", Prompt).load_text(command)
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        if command == "/help":
            assert isinstance(app.screen, DetailScreen)
        elif command.startswith("/theme"):
            assert app.settings.theme == "ember"
        else:
            assert app._exit


async def test_quit_button_and_repeated_exit_finish_cleanup():
    class Server:
        def __init__(self):
            self.started = asyncio.Event()
            self.release = asyncio.Event()
            self.finished = False

        async def close(self):
            self.started.set()
            await self.release.wait()
            self.finished = True

    app = Prism(Settings(record=False), offline=True)
    server = Server()
    async with app.run_test(size=(80, 24)) as pilot:
        app.server = server
        await pilot.click("#quit-app")
        await asyncio.wait_for(server.started.wait(), 2)
        await pilot.press("ctrl+q", "ctrl+q")
        assert not app._exit and not server.finished
        server.release.set()
        await pilot.pause()
        assert app._exit and server.finished
