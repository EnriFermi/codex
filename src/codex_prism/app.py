from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.theme import Theme
from textual.widgets import Button, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from .commands import command_help, suggestions
from .config import Settings, state_path
from .model import Entry, Trace, pretty
from .storage import Journal, export_markdown, private_write
from .transport import AppServer
from .widgets import COLORS, ICONS, DetailScreen, Prompt, RequestScreen, TraceCard

HELP = """Codex Prism · keyboard guide

Esc             Leave the composer / search; navigate the trace
j / k           Next / previous visible event
i               Focus the multiline composer
Enter           Send prompt (Ctrl+Enter / Alt+Enter also work)
Shift+Enter     New line (Ctrl+N works in legacy terminals)
/               Search full commands, reasoning, and output
o               Expand / collapse selected output
O               Expand / collapse all outputs
y / Y           Copy full command / full output via terminal clipboard
f               Toggle follow mode (G jumps to the latest event)
Ctrl+B          Toggle sidebar
Ctrl+R          Reload appearance config
Ctrl+T          Cycle themes
Ctrl+E          Export the entire transcript to Markdown
Ctrl+J          Inspect selected event as JSON
Ctrl+X          Interrupt the active turn
Ctrl+Q          Exit (interrupts an active turn)
F1              This guide

Composer commands:
Type / for descriptions; ↑/↓ selects, Tab/Enter completes, Esc closes.
Press Enter again to execute the completed command.
/new            Start a new conversation
/resume UUID    Resume a Codex thread
/sessions       List recent Codex threads
/theme NAME     prism, ember, daylight
/export [PATH]  Save the full transcript (never overwrites)
/stop           Interrupt the active turn
/help           This guide

Mouse: click an event to select, click OUTPUT to fold, scroll normally.
The output preview is a view only. Copy/export retains all received text.
Large blocks are paged; Next/Previous navigate without losing data.
"""


class Prism(App):
    TITLE = "Codex Prism"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("escape", "navigate", "Navigate", show=False),
        Binding("ctrl+q", "close_app", "Quit", priority=True),
        Binding("ctrl+x", "interrupt", "Stop", priority=True),
        Binding("ctrl+r", "reload_config", "Reload", show=False),
        Binding("ctrl+t", "cycle_theme", "Theme"),
        Binding("ctrl+b", "sidebar", "Sidebar", show=False),
        Binding("ctrl+e", "export", "Export"),
        Binding("ctrl+j", "inspect", "Inspect", show=False),
        Binding("shift+g", "latest", "Latest", show=False),
        Binding("f1", "help", "Help"),
    ]

    def __init__(
        self,
        settings: Settings,
        *,
        trace: Trace | None = None,
        cwd: str = ".",
        binary: str = "codex",
        model: str | None = None,
        resume: str | None = None,
        overrides: list[str] | None = None,
        sandbox: str | None = None,
        approval: str | None = None,
        prompt: str | None = None,
        offline: bool = False,
    ):
        css_paths = [Path(__file__).with_name("app.tcss"), settings.css] if settings.css else None
        super().__init__(css_path=css_paths, watch_css=bool(settings.css))
        self.settings = settings
        self.trace = trace or Trace()
        self.cwd = str(Path(cwd).resolve())
        self.binary, self.selected_model, self.resume_id = binary, model, resume
        self.overrides, self.sandbox, self.approval = overrides or [], sandbox, approval
        self.initial_prompt = prompt
        self.offline = offline
        self.server: AppServer | None = None
        self.journal: Journal | None = None
        self.pending_events: deque[dict] = deque()
        self.pending_requests: asyncio.Queue = asyncio.Queue()
        self.cards: dict[str, TraceCard] = {}
        self.selected_id: str | None = None
        self.visible_ids: list[str] = []
        self.filter_kind = "all"
        self.search_term = ""
        self.follow = True
        self.ready = False
        self.sending = False
        self.flushing = False
        self.switching = False
        self._custom_keys: list[str] = []
        self._shutdown_started = False
        self._apply_theme()
        self._bind_keys()

    @property
    def main_screen(self):
        # App queries target the active modal; background updates belong to the
        # persistent trace screen, including while an approval is open.
        return self.screen_stack[0]

    def _apply_theme(self):
        p = self.settings.palette
        self.register_theme(
            Theme(
                name="prism-custom",
                primary=p["accent"],
                secondary=p["reasoning"],
                accent=p["accent"],
                foreground=p["foreground"],
                background=p["background"],
                surface=p["surface"],
                panel=p["panel"],
                error=p["error"],
                success=p["assistant"],
                warning=p["command"],
                dark=self.settings.theme != "daylight",
                variables={
                    "reasoning": p["reasoning"],
                    "command": p["command"],
                    "assistant": p["assistant"],
                    "user": p["user"],
                    "output": p["output"],
                    "text-muted": p["muted"],
                },
            )
        )
        # Reassign through a different value to refresh an existing custom theme.
        self.theme = "textual-dark"
        self.theme = "prism-custom"

    def _bind_keys(self):
        for key in self._custom_keys:
            self._bindings.key_to_bindings.pop(key, None)
        self._custom_keys.clear()
        actions = dict(
            next="next_entry",
            previous="previous_entry",
            input="focus_input",
            search="search",
            toggle_output="toggle_output",
            expand_all="expand_all",
            copy_command="copy_command",
            copy_output="copy_output",
            follow="follow",
        )
        for name, key in self.settings.keys.items():
            if name in actions:
                self.bind(key, actions[name], show=False)
                self._custom_keys.extend(part.strip() for part in key.split(","))

    def compose(self) -> ComposeResult:
        with Horizontal(id="topbar"):
            yield Static("◈  CODEX PRISM", id="brand")
            yield Static("Connecting…", id="session-status", markup=False)
        yield Static(self.trace.cwd or self.cwd, id="workspace", markup=False)
        with Horizontal(id="main"):
            with Vertical(id="sidebar"):
                yield Static("TRACE EXPLORER", id="outline-title")
                with Horizontal(id="filters"):
                    yield Button("All", id="filter-all", classes="active")
                    yield Button("◇", id="filter-reasoning")
                    yield Button("$", id="filter-tools")
                    yield Button("◆", id="filter-messages")
                yield OptionList(id="outline", wrap=False)
                yield Static(
                    "j / k  navigate\no      fold output\n/      search\ni      write a prompt",
                    id="sidebar-note",
                )
            with Vertical(id="content"):
                yield Input(
                    placeholder="Search all received text, including folded output…", id="search"
                )
                with VerticalScroll(id="timeline", can_focus=True):
                    yield Static(
                        "◈  A clearer view of Codex\n\nCommands, reasoning, and results each have their own place.\nStart a conversation below. Press F1 for shortcuts.\n\nEnter sends · / opens command suggestions",
                        id="empty",
                        markup=False,
                    )
                with Vertical(id="composer-shell"):
                    yield Static("›  MESSAGE", id="composer-label")
                    menu = OptionList(id="command-menu", wrap=True)
                    menu.can_focus = False
                    yield menu
                    yield Static(command_help(""), id="composer-help", markup=False)
                    with Horizontal(id="composer-row"):
                        yield Prompt(id="composer", soft_wrap=True, show_line_numbers=False)
                        yield Button("Send", id="send-prompt", variant="primary")
        yield Static("", id="hint", markup=False)
        yield Footer()

    async def on_mount(self):
        self.main_screen.query_one("#command-menu").display = False
        self.main_screen.query_one("#command-menu").styles.max_height = min(
            9, max(3, self.size.height - 25)
        )
        self.main_screen.query_one("#search").display = False
        self.main_screen.query_one("#sidebar").display = self.settings.show_sidebar
        for entry in self.trace.entries.values():
            await self.add_card(entry)
        self.rebuild_outline()
        self.set_interval(0.12, self.flush_events)
        self.set_interval(0.5, self.refresh_status)
        self.approval_loop()
        if self.offline:
            self.ready = True
            self.main_screen.query_one("#composer-label", Static).update(
                "›  OFFLINE VIEW  ·  /help · /theme · /export"
            )
            self.action_navigate()
            if self.cards:
                self.select_entry(next(iter(self.cards)))
        else:
            self.connect()
            self.main_screen.query_one("#composer").focus()
        self.refresh_status()

    async def add_card(self, entry: Entry):
        if entry.id in self.cards:
            return
        card = TraceCard(entry, self.settings, len(self.cards) + 1)
        self.cards[entry.id] = card
        await self.main_screen.query_one("#timeline").mount(card)
        self.main_screen.query_one("#empty").display = False

    def incoming(self, message: dict):
        if self.journal:
            self.journal.write(message)
        if "id" in message and "method" in message:
            self.pending_requests.put_nowait(message)
        else:
            self.pending_events.append(message)

    def sent(self, message: dict):
        if self.journal:
            self.journal.write(message, "client")

    async def flush_events(self):
        if (
            self.flushing
            or self.switching
            or not self.pending_events
            or not self.screen_stack
            or not self.main_screen.query("#timeline")
        ):
            return
        self.flushing = True
        try:
            changed: dict[str, Entry] = {}
            while self.pending_events:
                for entry in self.trace.reduce(self.pending_events.popleft()):
                    changed[entry.id] = entry
            new_entries = False
            for entry in changed.values():
                if entry.id not in self.cards:
                    await self.add_card(entry)
                    new_entries = True
                else:
                    self.cards[entry.id].refresh_entry()
            if changed:
                self.rebuild_outline()
                if self.follow:
                    if new_entries:
                        self.selected_id = next(reversed(self.cards))
                        self.mark_selected()
                    self.main_screen.query_one("#timeline", VerticalScroll).scroll_end(
                        animate=False
                    )
            self.refresh_status()
        finally:
            self.flushing = False

    def rebuild_outline(self):
        outline = self.main_screen.query_one("#outline", OptionList)
        old_selected = self.selected_id
        self.visible_ids = []
        options = []
        for key, card in self.cards.items():
            entry = card.entry
            group_match = (
                self.filter_kind == "all"
                or self.filter_kind == "reasoning"
                and entry.kind == "reasoning"
                or self.filter_kind == "tools"
                and entry.kind in {"command", "tool", "file"}
                or self.filter_kind == "messages"
                and entry.kind in {"assistant", "commentary", "user"}
            )
            visible = group_match and (
                not self.search_term or self.search_term.casefold() in entry.searchable.casefold()
            )
            card.display = visible
            if visible:
                self.visible_ids.append(key)
                color = self.settings.palette.get(
                    COLORS.get(entry.kind, entry.kind), self.settings.palette["muted"]
                )
                label = Text(
                    f"{card.number:02d} {ICONS.get(entry.kind, '·')} ",
                    style=color,
                    no_wrap=True,
                    overflow="ellipsis",
                )
                label.append(
                    entry.title.replace("\n", " "), style=self.settings.palette["foreground"]
                )
                options.append(Option(label, id=card.id))
        outline.clear_options()
        outline.add_options(options)
        if old_selected in self.visible_ids:
            outline.highlighted = self.visible_ids.index(old_selected)
        elif self.visible_ids:
            self.selected_id = self.visible_ids[0]
            outline.highlighted = 0
        self.mark_selected()
        self.main_screen.query_one("#outline-title", Static).update(
            f"TRACE EXPLORER   {len(self.visible_ids)}"
        )

    def mark_selected(self):
        for key, card in self.cards.items():
            card.set_class(key == self.selected_id, "selected")

    def select_entry(self, key: str):
        if key not in self.cards:
            return
        self.selected_id = key
        self.follow = False
        self.mark_selected()
        self.cards[key].scroll_visible(top=True, animate=False)
        if key in self.visible_ids:
            self.main_screen.query_one("#outline", OptionList).highlighted = self.visible_ids.index(
                key
            )
        self.refresh_status()

    @on(TraceCard.Selected)
    def card_selected(self, event: TraceCard.Selected):
        self.selected_id = event.entry_id
        self.follow = False
        self.mark_selected()
        self.refresh_status()

    @on(OptionList.OptionSelected, "#outline")
    def outline_selected(self, event: OptionList.OptionSelected):
        if event.option_index < len(self.visible_ids):
            self.select_entry(self.visible_ids[event.option_index])

    @on(Button.Pressed, "#filters Button")
    def set_filter(self, event: Button.Pressed):
        self.filter_kind = event.button.id.removeprefix("filter-")
        for button in self.main_screen.query("#filters Button"):
            button.set_class(button is event.button, "active")
        self.rebuild_outline()

    @on(Input.Changed, "#search")
    def search_changed(self, event: Input.Changed):
        self.search_term = event.value
        self.follow = False
        self.rebuild_outline()

    def refresh_status(self):
        if not self.screen_stack or not self.main_screen.query("#session-status"):
            return
        mode = (
            "DEMO"
            if self.trace.status == "demo"
            else "REPLAY"
            if self.offline
            else self.trace.status.upper()
        )
        usage = self.trace.usage.get("last", {})
        token_label = f"  ·  {usage['totalTokens']:,} tokens" if usage.get("totalTokens") else ""
        label = f"{self.trace.model or 'Codex'}  ·  {mode}{token_label}"
        self.main_screen.query_one("#session-status", Static).update(label)
        self.main_screen.query_one("#workspace", Static).update(
            f"{self.trace.cwd or self.cwd}  ·  {self.trace.thread_id or 'new session'}"
        )
        recorder = "recording" if self.journal else "offline" if self.offline else "no recording"
        self.main_screen.query_one("#hint", Static).update(
            f"{'● FOLLOW' if self.follow else '○ BROWSE'}  ·  {recorder}  ·  {len(self.trace.entries)} events  ·  Esc navigate  / search  o output  i compose"
        )

    @work(exclusive=True, group="connect")
    async def connect(self):
        try:
            if self.settings.record:
                self.journal = Journal(state_path() / "traces", self.settings.compress_recordings)
            self.server = AppServer(self.binary, self.overrides, self.incoming, self.sent)
            await self.server.start()
            await self.open_thread(self.resume_id)
            self.ready = True
            if self.initial_prompt:
                self.send_prompt(self.initial_prompt)
        except Exception as exc:
            self.trace.status = "disconnected"
            self.incoming(
                {"method": "prism/error", "params": {"message": f"Could not connect: {exc}"}}
            )

    async def open_thread(self, resume_id: str | None = None):
        params = {}
        if self.selected_model:
            params["model"] = self.selected_model
        if self.sandbox:
            params["sandbox"] = self.sandbox
        if self.approval:
            params["approvalPolicy"] = self.approval
        if resume_id:
            params["threadId"] = resume_id
            result = await self.server.request("thread/resume", params)
        else:
            params["cwd"] = self.cwd
            result = await self.server.request("thread/start", params)
        thread = result["thread"]
        self.trace.thread_id = thread["id"]
        self.trace.cwd = result.get("cwd", thread.get("cwd", self.cwd))
        self.trace.model = result.get("model", "Codex")
        self.incoming(
            {
                "method": "prism/session",
                "params": {
                    "thread_id": self.trace.thread_id,
                    "cwd": self.trace.cwd,
                    "model": self.trace.model,
                },
            }
        )
        turns = thread.get("turns") or []
        if resume_id and thread.get("historyMode") == "paginated":
            turns = []
            cursor = None
            while True:
                page = await self.server.request(
                    "thread/turns/list",
                    {
                        "threadId": resume_id,
                        "itemsView": "full",
                        "sortDirection": "asc",
                        "limit": 100,
                        **({"cursor": cursor} if cursor else {}),
                    },
                )
                turns.extend(page["data"])
                cursor = page.get("nextCursor")
                if not cursor:
                    break
        if turns:
            self.incoming({"method": "prism/history", "params": {"turns": turns}})
        self.trace.status = "ready"
        self.incoming(
            {
                "method": "prism/note",
                "params": {
                    "text": f"Connected · {self.trace.model} · {self.trace.thread_id}\n{self.trace.cwd}\nSandbox: {result.get('sandbox', {}).get('type', 'inherited')} · approvals: {pretty(result.get('approvalPolicy', 'inherited'))}"
                },
            }
        )

    @on(Prompt.Submitted)
    def prompt_submitted(self, event: Prompt.Submitted):
        self.send_prompt(event.text)

    @on(Button.Pressed, "#send-prompt")
    def send_pressed(self):
        self.main_screen.query_one("#composer", Prompt).action_submit()

    @on(Prompt.Changed, "#composer")
    def update_command_menu(self):
        prompt = self.main_screen.query_one("#composer", Prompt)
        menu = self.main_screen.query_one("#command-menu", OptionList)
        matches = suggestions(prompt.text)
        menu.clear_options()
        menu.add_options(
            Option(Text.assemble((f"{c.usage:<17}", "bold"), c.description), id=c.text)
            for c in matches
        )
        menu.display = prompt.completion_open = bool(matches)
        if matches:
            menu.highlighted = 0
        self.main_screen.query_one("#composer-help", Static).update(
            "↑/↓ choose · Tab / Enter complete · Esc close"
            if matches
            else command_help(prompt.text)
        )

    def complete_command(self, text: str):
        prompt = self.main_screen.query_one("#composer", Prompt)
        prompt.load_text(text)
        prompt.move_cursor((0, len(text)))
        prompt.focus()

    @on(Prompt.Completion)
    def command_key(self, event: Prompt.Completion):
        menu = self.main_screen.query_one("#command-menu", OptionList)
        if event.action == "escape":
            menu.display = False
            prompt = self.main_screen.query_one("#composer", Prompt)
            prompt.completion_open = False
            self.main_screen.query_one("#composer-help", Static).update(command_help(prompt.text))
        elif event.action in {"up", "down"}:
            step = -1 if event.action == "up" else 1
            menu.highlighted = ((menu.highlighted or 0) + step) % menu.option_count
        elif menu.highlighted is not None:
            self.complete_command(menu.get_option_at_index(menu.highlighted).id)

    @on(OptionList.OptionSelected, "#command-menu")
    def command_selected(self, event: OptionList.OptionSelected):
        event.stop()
        self.complete_command(event.option.id)

    @work(group="send")
    async def send_prompt(self, text: str):
        if self.sending:
            return
        self.sending = True
        try:
            if text.startswith("/"):
                await self.slash_command(text)
                self.main_screen.query_one("#composer", Prompt).load_text("")
                return
            if not self.ready or not self.server or self.offline:
                self.notify(
                    "Start a live session to send prompts. Offline mode supports /help, /theme and /export.",
                    severity="warning",
                )
                return
            params = {"threadId": self.trace.thread_id, "input": [{"type": "text", "text": text}]}
            if self.trace.turn_id:
                params["expectedTurnId"] = self.trace.turn_id
                await self.server.request("turn/steer", params)
            else:
                result = await self.server.request("turn/start", params)
                self.trace.turn_id = result["turn"]["id"]
                self.trace.status = "working"
            self.main_screen.query_one("#composer", Prompt).load_text("")
            self.follow = True
        except Exception as exc:
            self.notify(str(exc), title="Codex", severity="error", timeout=10)
        finally:
            self.sending = False

    async def slash_command(self, text: str):
        command, _, arg = text.strip().partition(" ")
        arg = arg.strip()
        if command == "/help":
            self.action_help()
        elif command == "/theme":
            if arg not in {"prism", "ember", "daylight"}:
                raise ValueError("Use /theme prism, ember, or daylight")
            self.settings.theme = arg
            self.redraw_theme()
        elif command == "/export":
            self.export_trace(Path(arg).expanduser() if arg else None)
        elif command == "/stop":
            await self.interrupt_turn()
        elif command in {"/new", "/resume", "/sessions"}:
            if not self.server or not self.ready:
                raise ValueError("Not connected to Codex")
            if command == "/sessions":
                result = await self.server.request(
                    "thread/list", {"limit": 30, "sortKey": "updated_at"}
                )
                listing = "\n\n".join(
                    f"{t['id']}\n{t.get('name') or t.get('preview', '')}\n{t.get('cwd', '')}"
                    for t in result.get("data", [])
                )
                self.push_screen(
                    DetailScreen("Recent sessions · /resume UUID", listing, self.settings, "text")
                )
            else:
                if self.trace.turn_id:
                    raise ValueError("Stop the active turn with Ctrl+X before switching sessions")
                if command == "/resume" and not arg:
                    raise ValueError("Use /resume UUID")
                await self.flush_events()
                self.switching = True
                old_trace = self.trace
                self.trace = Trace()
                try:
                    await self.open_thread(arg if command == "/resume" else None)
                    for card in self.cards.values():
                        await card.remove()
                    self.cards.clear()
                    self.selected_id = None
                    self.rebuild_outline()
                except Exception:
                    self.trace = old_trace
                    raise
                finally:
                    self.switching = False
        else:
            raise ValueError(f"Unknown command: {command}. Use /help")

    @work(group="approvals")
    async def approval_loop(self):
        while True:
            request = await self.pending_requests.get()
            try:
                method = request["method"]
                supported = method in {
                    "item/commandExecution/requestApproval",
                    "item/fileChange/requestApproval",
                    "item/permissions/requestApproval",
                    "item/tool/requestUserInput",
                    "mcpServer/elicitation/request",
                }
                if not supported:
                    await self.server.respond(
                        request["id"],
                        error={
                            "code": -32601,
                            "message": f"Codex Prism does not implement {method}",
                        },
                    )
                    self.notify(f"Unsupported server request: {method}", severity="warning")
                    continue
                result = await self.push_screen_wait(RequestScreen(request, self.settings))
                await self.server.respond(request["id"], result)
            except Exception as exc:
                self.notify(str(exc), title="Approval", severity="error")
            finally:
                self.pending_requests.task_done()

    def on_resize(self, event):
        if self.is_mounted and self.screen_stack and self.main_screen.query("#sidebar"):
            self.main_screen.query_one("#command-menu").styles.max_height = min(
                9, max(3, event.size.height - 25)
            )
            self.main_screen.query_one("#sidebar").display = (
                self.settings.show_sidebar and event.size.width >= 96
            )

    def on_mouse_scroll_up(self):
        self.follow = False
        self.refresh_status()

    def on_key(self, event):
        if event.key in {"pageup", "home"} and not isinstance(self.focused, (Prompt, Input)):
            self.follow = False

    def action_navigate(self):
        self.main_screen.query_one("#timeline").focus()
        self.follow = False

    def action_focus_input(self):
        self.main_screen.query_one("#composer").focus()

    def move_entry(self, delta: int):
        if not self.visible_ids:
            return
        index = (
            self.visible_ids.index(self.selected_id) if self.selected_id in self.visible_ids else -1
        )
        index = max(0, min(len(self.visible_ids) - 1, index + delta))
        self.select_entry(self.visible_ids[index])

    def action_next_entry(self):
        self.move_entry(1)

    def action_previous_entry(self):
        self.move_entry(-1)

    def action_search(self):
        self.main_screen.query_one("#search").display = True
        self.main_screen.query_one("#search").focus()

    def action_toggle_output(self):
        if card := self.cards.get(self.selected_id):
            card.toggle_output()

    def action_expand_all(self):
        expand = not any(c.expanded for c in self.cards.values())
        for card in self.cards.values():
            card.expanded = expand
            card.refresh_output()

    def action_copy_command(self):
        if card := self.cards.get(self.selected_id):
            self.copy_to_clipboard(
                card.entry.command
                or card.entry.text
                or card.entry.content_text
                or card.entry.summary_text
            )
            self.notify("Copied full text (terminal clipboard / OSC 52)")

    def action_copy_output(self):
        if card := self.cards.get(self.selected_id):
            self.copy_to_clipboard(card.entry.output)
            self.notify("Copied full received output (terminal clipboard / OSC 52)")

    def action_follow(self):
        self.follow = not self.follow
        if self.follow:
            self.main_screen.query_one("#timeline", VerticalScroll).scroll_end(animate=False)
        self.refresh_status()

    def action_latest(self):
        self.follow = True
        self.main_screen.query_one("#timeline", VerticalScroll).scroll_end(animate=False)

    def action_sidebar(self):
        sidebar = self.main_screen.query_one("#sidebar")
        sidebar.display = not sidebar.display

    def redraw_theme(self):
        self._apply_theme()
        for card in self.cards.values():
            card.settings = self.settings
            for widget in card.query("PagedText"):
                widget.settings = self.settings
            card.refresh_entry()
        self.rebuild_outline()

    def action_reload_config(self):
        try:
            settings = Settings.load(
                self.settings.path if self.settings.path and self.settings.path.exists() else None
            )
            self.settings = settings
            self._bind_keys()
            self.redraw_theme()
            self.main_screen.query_one("#sidebar").display = settings.show_sidebar
            self.notify("Appearance reloaded")
        except Exception as exc:
            self.notify(str(exc), severity="error", title="Config unchanged")

    def action_cycle_theme(self):
        themes = ["prism", "ember", "daylight"]
        self.settings.theme = themes[(themes.index(self.settings.theme) + 1) % len(themes)]
        self.redraw_theme()
        self.notify(self.settings.theme, title="Theme")

    def action_help(self):
        self.push_screen(DetailScreen("Keyboard & commands", HELP, self.settings, "text"))

    def action_inspect(self):
        if card := self.cards.get(self.selected_id):
            self.push_screen(
                DetailScreen(
                    "Event inspector · source item and assembled content",
                    pretty(
                        {
                            "item": card.entry.raw,
                            "received": {
                                "command": card.entry.command,
                                "output": card.entry.output,
                                "text": card.entry.text,
                                "reasoningContent": card.entry.content,
                                "reasoningSummary": card.entry.summary,
                            },
                        }
                    ),
                    self.settings,
                )
            )

    def export_trace(self, path: Path | None = None):
        path = (
            path
            or state_path()
            / "exports"
            / f"trace-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}.md"
        )
        private_write(path, export_markdown(self.trace))
        self.notify(str(path), title="Full transcript exported", timeout=12)
        return path

    def action_export(self):
        try:
            self.export_trace()
        except Exception as exc:
            self.notify(str(exc), severity="error")

    async def interrupt_turn(self):
        if self.server and self.trace.turn_id:
            await self.server.request(
                "turn/interrupt", {"threadId": self.trace.thread_id, "turnId": self.trace.turn_id}
            )
            self.notify("Interrupt requested")

    @work(group="interrupt", exclusive=True)
    async def action_interrupt(self):
        try:
            await self.interrupt_turn()
        except Exception as exc:
            self.notify(str(exc), severity="error")

    @work(group="close", exclusive=True)
    async def action_close_app(self):
        if not self._shutdown_started:
            self._shutdown_started = True
            try:
                await asyncio.wait_for(self.interrupt_turn(), 3)
            except Exception:
                pass
            if self.server:
                await self.server.close()
            if self.journal:
                self.journal.close()
        self.exit()

    async def on_unmount(self):
        if self.server:
            await self.server.close()
        if self.journal:
            self.journal.close()
