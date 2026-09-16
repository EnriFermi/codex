from textual.widgets import Input

from codex_prism.app import Prism
from codex_prism.config import Settings
from codex_prism.demo import demo_trace
from codex_prism.widgets import RequestScreen


async def test_approval_requires_explicit_choice():
    app = Prism(Settings(), trace=demo_trace(), offline=True)
    results = []
    async with app.run_test(size=(100, 40)) as pilot:
        screen = RequestScreen(
            {
                "id": 3,
                "method": "item/commandExecution/requestApproval",
                "params": {"command": "echo test", "cwd": "/tmp", "reason": "test request"},
            },
            app.settings,
        )
        app.push_screen(screen, results.append)
        await pilot.pause()
        assert results == []
        await pilot.click("#request-decline")
        await pilot.pause()
        assert results == [{"decision": "decline"}]


async def test_request_input_uses_question_ids_and_escape_cancels():
    app = Prism(Settings(), trace=demo_trace(), offline=True)
    results = []
    request = {
        "id": "req",
        "method": "item/tool/requestUserInput",
        "params": {
            "questions": [{"id": "choice", "question": "Choose", "options": [{"label": "A"}]}]
        },
    }
    async with app.run_test(size=(100, 40)) as pilot:
        app.push_screen(RequestScreen(request, app.settings), results.append)
        await pilot.pause()
        app.screen.query_one("#answer-0", Input).value = "A"
        await pilot.click("#request-answers")
        await pilot.pause()
        assert results[-1] == {"answers": {"choice": {"answers": ["A"]}}}
        app.push_screen(RequestScreen(request, app.settings), results.append)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert results[-1] == {"answers": {"choice": {"answers": []}}}


async def test_permission_cancel_grants_nothing():
    app = Prism(Settings(), trace=demo_trace(), offline=True)
    results = []
    request = {
        "id": "p",
        "method": "item/permissions/requestApproval",
        "params": {"permissions": {"network": {"enabled": True}}},
    }
    async with app.run_test(size=(80, 28)) as pilot:
        app.push_screen(RequestScreen(request, app.settings), results.append)
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert results[-1] == {"permissions": {}, "scope": "turn"}
