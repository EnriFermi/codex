import asyncio
from pathlib import Path

import pytest
from textual.widgets import Button

from codex_prism.app import Prism
from codex_prism.config import Settings
from codex_prism.session_settings import ChoiceScreen, SessionSettings, list_models
from codex_prism.transport import RpcError
from codex_prism.widgets import Prompt


def initial_response():
    return {
        "thread": {"id": "test-thread"},
        "model": "test-model",
        "reasoningEffort": "medium",
        "approvalPolicy": "on-request",
        "sandbox": {"type": "readOnly"},
        "approvalsReviewer": "user",
        "activePermissionProfile": {"id": ":read-only"},
    }


async def ready(app, pilot):
    async with asyncio.timeout(5):
        while not app.ready:
            await pilot.pause(0.01)


async def command(app, pilot, text):
    app.main_screen.query_one("#composer", Prompt).load_text(text)
    await pilot.press("ctrl+enter")
    await pilot.pause()


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
async def test_permissions_cancel_then_confirm_full_access(size):
    app = Prism(Settings(record=False), binary=str(Path(__file__).with_name("fake_server.py")))
    async with app.run_test(size=size) as pilot:
        await ready(app, pilot)
        calls = []
        request = app.server.request

        async def tracked(method, params, **kwargs):
            calls.append((method, params))
            return await request(method, params, **kwargs)

        app.server.request = tracked
        await command(app, pilot, "/permissions")
        assert isinstance(app.screen, ChoiceScreen)
        # Full access must remain a draft while highlighted or selected.
        await pilot.press("end", "enter")
        assert app.screen.query_one("#settings-apply", Button).has_focus
        assert not calls
        await pilot.press("escape")
        assert not calls and app.session_settings.values["approvalPolicy"] == "on-request"
        await command(app, pilot, "/permissions")
        await pilot.press("end", "enter")
        await pilot.click("#settings-apply")
        await pilot.pause()
        assert calls == [
            (
                "thread/settings/update",
                {
                    "threadId": "test-thread",
                    "permissions": ":danger-full-access",
                    "approvalPolicy": "never",
                    "approvalsReviewer": "user",
                },
            )
        ]
        assert app.session_settings.values["sandboxPolicy"]["type"] == "dangerFullAccess"
        assert app.trace.thread_id == "test-thread"


async def test_model_and_effort_apply_together_and_cancel_changes_neither():
    app = Prism(Settings(record=False), binary=str(Path(__file__).with_name("fake_server.py")))
    async with app.run_test(size=(80, 24)) as pilot:
        await ready(app, pilot)
        before = app.session_settings.values.copy()
        for cancel in (True, False):
            await command(app, pilot, "/model")
            await pilot.click("#settings-apply")
            await pilot.pause()
            assert app.screen.heading == "Reasoning effort"
            await pilot.press("end")
            assert app.session_settings.values == before
            if cancel:
                await pilot.press("escape")
                assert app.session_settings.values == before
            else:
                await pilot.click("#settings-apply")
                await pilot.pause()
                assert app.session_settings.values["effort"] == "high"


@pytest.mark.parametrize("command_text", ["/permissions", "/model"])
async def test_settings_cannot_change_while_turn_is_running(command_text):
    app = Prism(Settings(record=False), binary=str(Path(__file__).with_name("fake_server.py")))
    async with app.run_test(size=(80, 24)) as pilot:
        await ready(app, pilot)
        app.trace.turn_id = "busy"
        await command(app, pilot, command_text)
        assert len(app.screen_stack) == 1
        assert app.query_one("#composer", Prompt).text == command_text
        assert app.session_settings.values["approvalPolicy"] == "on-request"


async def test_acknowledgement_does_not_mean_settings_applied():
    state = SessionSettings(initial_response())
    ack = asyncio.Event()

    class Server:
        async def request(self, method, params):
            assert method == "thread/settings/update"
            ack.set()
            return {}

    task = asyncio.create_task(state.apply(Server(), {"effort": "high"}))
    await ack.wait()
    assert not task.done() and state.values["effort"] == "medium"
    state.incoming(
        {
            "method": "thread/settings/updated",
            "params": {
                "threadId": "other-thread",
                "threadSettings": {"effort": "low"},
            },
        }
    )
    assert not task.done() and state.values["effort"] == "medium"
    state.incoming(
        {
            "method": "thread/settings/updated",
            "params": {
                "threadId": "test-thread",
                "threadSettings": {**state.values, "effort": "high"},
            },
        }
    )
    assert await task
    assert state.values["effort"] == "high"


@pytest.mark.parametrize("rejected", [True, False])
async def test_rejected_or_unapplied_settings_never_report_success(rejected):
    state = SessionSettings(initial_response())
    before = state.values.copy()

    class Server:
        async def request(self, method, params):
            if method == "thread/settings/update":
                if rejected:
                    raise RpcError({"message": "Disabled by requirements"})
                return {}
            assert method == "thread/resume" and params["excludeTurns"] is True
            return initial_response()

    with pytest.raises((RpcError, ValueError)):
        await state.apply(Server(), {"approvalPolicy": "never"}, timeout=0.01)
    assert state.values == before and state.waiter is None


async def test_noop_and_unchanged_event_suppression():
    state = SessionSettings(initial_response())
    assert not await state.apply(None, {"approvalPolicy": "on-request"})

    class Server:
        async def request(self, method, params):
            return {} if method == "thread/settings/update" else initial_response()

    state.values["effort"] = "low"  # Simulate a stale view; backend is already medium.
    assert await state.apply(Server(), {"effort": "medium"}, timeout=0.01)


async def test_model_picker_reads_all_pages_and_omits_hidden_models():
    class Server:
        async def request(self, method, params):
            assert method == "model/list"
            if params.get("cursor"):
                return {"data": [{"model": "second"}], "nextCursor": None}
            return {
                "data": [{"model": "first"}, {"model": "hidden", "hidden": True}],
                "nextCursor": "page2",
            }

    assert [m["model"] for m in await list_models(Server())] == ["first", "second"]
