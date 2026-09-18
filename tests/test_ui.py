import pytest
from textual.events import Paste
from textual.widgets import Input, OptionList

from codex_prism.app import Prism
from codex_prism.config import Settings
from codex_prism.demo import demo_trace
from codex_prism.widgets import PagedText, Prompt


async def test_demo_navigation_search_fold_and_theme(tmp_path):
    app = Prism(Settings(), trace=demo_trace(), offline=True)
    async with app.run_test(size=(132, 44)) as pilot:
        await pilot.pause()
        assert len(app.cards) == 7
        app.select_entry("demo-search")
        await pilot.press("o")
        assert app.cards["demo-search"].expanded
        await pilot.press("o")
        assert not app.cards["demo-search"].expanded
        await pilot.press("j")
        assert app.selected_id == "demo-commentary"
        await pilot.press("slash")
        app.query_one("#search", Input).value = "test_case_24"
        await pilot.pause()
        assert app.visible_ids == ["demo-tests"]
        app.query_one("#search", Input).value = ""
        await pilot.press("escape")
        await pilot.press("ctrl+t")
        assert app.settings.theme == "ember"
        exported = app.export_trace(tmp_path / "trace.md")
        assert "test_case_24" in exported.read_text()
        app.save_screenshot("demo.svg", path=str(tmp_path))
        assert (tmp_path / "demo.svg").stat().st_size > 1000


async def test_large_output_is_paged_without_data_loss():
    t = demo_trace()
    t.entries["demo-search"].output = "\n".join(f"line-{i}" for i in range(10000))
    app = Prism(Settings(page_lines=100), trace=t, offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.select_entry("demo-search")
        app.action_toggle_output()
        await pilot.pause()
        body = app.cards["demo-search"].query_one(".output-body", PagedText)
        assert "line-9999" in body.value
        assert body.page == 0
        body.page = 99
        body.refresh_text()
        assert body.page == 99
        assert len(t.entries["demo-search"].output.splitlines()) == 10000


async def test_typing_does_not_trigger_navigation_and_narrow_resize():
    app = Prism(Settings(), trace=demo_trace(), offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        selected = app.selected_id
        await pilot.press("i")
        await pilot.press("j", "k", "o", "f", "slash", "y")
        from codex_prism.widgets import Prompt

        assert app.query_one("#composer", Prompt).text == "jkof/y"
        assert app.selected_id == selected
        await pilot.resize_terminal(80, 24)
        await pilot.pause()
        assert app.query_one("#timeline").size.width > 50


async def test_config_reload_removes_old_keybinding(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('[keys]\nnext="n"\n')
    app = Prism(Settings.load(p), trace=demo_trace(), offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        app.select_entry("demo-user")
        await pilot.press("n")
        assert app.selected_id == "demo-reasoning"
        p.write_text('[keys]\nnext="l"\n')
        app.action_reload_config()
        await pilot.pause()
        await pilot.press("n")
        assert app.selected_id == "demo-reasoning"
        await pilot.press("l")
        assert app.selected_id == "demo-search"


@pytest.mark.parametrize("send", ["enter", "ctrl+enter", "ctrl+j", "alt+enter", "button"])
async def test_live_client_prompt_to_full_command_to_completion(tmp_path, send):
    import asyncio
    from pathlib import Path

    from codex_prism.widgets import Prompt

    app = Prism(
        Settings(record=False),
        binary=str(Path(__file__).with_name("fake_server.py")),
        cwd=str(tmp_path),
    )
    async with app.run_test(size=(120, 42)) as pilot:
        async with asyncio.timeout(5):
            while not app.ready:
                await pilot.pause(0.05)
        app.query_one("#composer", Prompt).load_text("Run the smoke check")
        if send == "button":
            await pilot.click("#send-prompt")
        else:
            await pilot.press(send)
        async with asyncio.timeout(5):
            while app.trace.status != "completed":
                await pilot.pause(0.05)
        await pilot.pause()
        assert app.trace.entries["c"].output == "hello\n"
        assert app.trace.entries["c"].command == "printf 'hello\\n'"
        assert app.trace.entries["a"].text == "Test complete."
        assert app.query_one("#composer", Prompt).text == ""
        assert app.trace.turn_id == ""
        assert app.cards["c"].entry.exit_code == 0
    assert app.server.process.returncode is not None


async def test_multiline_and_paste_never_submit():
    app = Prism(Settings(record=False), offline=True)
    sent = []
    app.send_prompt = sent.append
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("i", "a", "shift+enter", "b", "ctrl+n", "c")
        prompt = app.query_one("#composer", Prompt)
        assert prompt.text == "a\nb\nc"
        app.post_message(Paste("\npasted\ntext\n"))
        await pilot.pause()
        assert prompt.text == "a\nb\nc\npasted\ntext\n"
        assert sent == []
        await pilot.press("enter")
        assert sent == [prompt.text]


async def test_slash_menu_filter_navigation_completion_and_escape():
    app = Prism(Settings(record=False), offline=True)
    sent = []
    app.send_prompt = sent.append
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("i", "slash")
        menu = app.query_one("#command-menu", OptionList)
        prompt = app.query_one("#composer", Prompt)
        assert menu.display and menu.option_count == 9
        assert app.query_one("#timeline").size.height > 0
        await pilot.press("down", "tab")
        assert prompt.text == "/resume "
        assert prompt.has_focus and not menu.display
        assert sent == []
        prompt.load_text("/th")
        await pilot.pause()
        assert menu.option_count == 1
        await pilot.press("enter")
        assert prompt.text == "/theme "
        assert menu.option_count == 3
        await pilot.press("down", "enter")
        assert prompt.text == "/theme ember"
        assert not menu.display
        assert sent == ["/theme ember"]
        prompt.load_text("/")
        await pilot.pause()
        await pilot.press("escape")
        assert not menu.display and prompt.has_focus
        await pilot.press("escape")
        assert not prompt.has_focus


async def test_slash_menu_mouse_selection_and_unknown_command_preserve_draft():
    app = Prism(Settings(record=False), offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.press("i", "slash", "h")
        await pilot.click("#command-menu", offset=(3, 1))
        from codex_prism.widgets import DetailScreen

        assert isinstance(app.screen, DetailScreen)
        await pilot.press("escape")
        prompt = app.query_one("#composer", Prompt)
        assert prompt.text == "" and prompt.has_focus
        prompt.load_text("/unknown important draft")
        await pilot.pause()
        assert not app.query_one("#command-menu").display
        await pilot.press("enter")
        await pilot.pause()
        assert prompt.text == "/unknown important draft"


async def test_quit_closes_message_pump_cleanly():
    app = Prism(Settings(), trace=demo_trace(), offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+q")
        assert app._exit


async def test_custom_css_extends_base_layout(tmp_path):
    css = tmp_path / "custom.tcss"
    css.write_text("#sidebar { width: 24; }\n")
    app = Prism(Settings(css=css), trace=demo_trace(), offline=True)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.query_one("#sidebar").size.width == 23  # border occupies one cell
        assert app.query_one("#topbar").size.height == 2  # padding occupies one cell
        assert app.query_one("#timeline").size.height > 15
