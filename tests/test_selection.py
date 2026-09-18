from textual.geometry import Offset
from textual.selection import Selection
from textual.widgets import TextArea

from codex_prism.app import Prism
from codex_prism.config import Settings
from codex_prism.model import Entry, Trace
from codex_prism.selectable import SelectableText


def trace_for_copy():
    trace = Trace()
    trace.entries["copy"] = Entry(
        id="copy", kind="assistant", text=r"Select **these words** and \(x^2\).", status="completed"
    )
    return trace


async def test_drag_and_copy_rendered_markdown_with_composer_focused():
    app = Prism(Settings(record=False), trace=trace_for_copy(), offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.press("i")
        body = app.cards["copy"].query_one(".page-body", SelectableText)
        assert body.render().plain.startswith("Select these words and x².")
        await pilot.mouse_down(body, offset=(7, 0))
        await pilot.hover(body, offset=(17, 0))
        await pilot.mouse_up(body, offset=(17, 0))
        await pilot.pause()
        assert app.screen.get_selected_text() == "these words"
        await pilot.press("ctrl+c")
        assert app.clipboard == "these words" and not app._exit
        assert not app.follow


async def test_copy_button_includes_full_source_and_selection_pauses_updates():
    trace = trace_for_copy()
    original = trace.entries["copy"].text
    app = Prism(Settings(record=False), trace=trace, offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        body = app.cards["copy"].query_one(".page-body", SelectableText)
        app.screen.selections = {body: Selection(Offset(0, 0), Offset(6, 0))}
        app.incoming(
            {
                "method": "item/agentMessage/delta",
                "params": {"itemId": "copy", "delta": " New text."},
            }
        )
        await app.flush_events()
        assert trace.entries["copy"].text == original
        await pilot.press("ctrl+c")
        assert app.clipboard == "Select"
        app.action_latest()
        await app.flush_events()
        await pilot.pause()
        assert trace.entries["copy"].text == original + " New text."
        await pilot.click(app.cards["copy"].query_one(".copy-entry"))
        assert app.clipboard == original + " New text."


async def test_composer_copy_still_works():
    from textual.widgets.text_area import Selection as EditorSelection

    app = Prism(Settings(record=False), offline=True)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("i")
        prompt = app.query_one("#composer", TextArea)
        prompt.load_text("copy part of this prompt")
        prompt.selection = EditorSelection((0, 5), (0, 9))
        await pilot.press("ctrl+c")
        assert app.clipboard == "part"


async def test_unwrapped_code_keeps_the_scrollable_tail():
    trace = Trace()
    command = "printf " + "x" * 500 + " TAIL_MARKER"
    trace.entries["long"] = Entry(id="long", kind="command", command=command, status="completed")
    app = Prism(Settings(record=False, wrap=False), trace=trace, offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        body = app.cards["long"].query_one(".command-body .page-body", SelectableText)
        assert "TAIL_MARKER" in body.render().plain
        viewport = body.parent
        assert viewport.max_scroll_x > 0
        viewport.scroll_to(x=viewport.max_scroll_x, animate=False)
        await pilot.pause()
        assert viewport.scroll_x > 0
        await pilot.click(app.cards["long"].query_one(".copy-entry"))
        assert app.clipboard == command
