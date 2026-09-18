"""Searchable, paginated session chooser using the public app-server API."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, OptionList, Static
from textual.widgets.option_list import Option

from .rendering import display_text
from .transport import AppServer


def session_label(thread: dict, current_id: str) -> Text:
    title = thread.get("name") or thread.get("preview") or "Untitled conversation"
    title = " ".join(display_text(title).split())
    cwd = display_text(thread.get("cwd", ""))
    try:
        updated = datetime.fromtimestamp(thread.get("updatedAt", 0), timezone.utc)
        date = updated.strftime("%d %b %Y · %H:%M UTC")
    except (ValueError, TypeError, OverflowError, OSError):
        date = "Unknown date"
    label = Text(title[:180], style="bold")
    if thread["id"] == current_id:
        label.append("  · current", style="italic")
    label.append(f"\n{date}   {cwd}", style="dim")
    return label


class SessionPicker(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, server: AppServer, cwd: str, current_id: str):
        super().__init__()
        self.server, self.cwd, self.current_id = server, cwd, current_id
        self.threads: dict[str, dict] = {}
        self.fetching = True
        self.load_error = ""
        self.workspace_only = False

    def compose(self):
        with Vertical(id="session-dialog"):
            yield Static("RESUME A CONVERSATION", classes="dialog-title")
            yield Input(placeholder="Search title, preview, directory…", id="session-search")
            yield Static("Loading saved conversations…", id="session-count", markup=False)
            yield OptionList(id="session-list")
            yield Static("", id="session-preview", markup=False)
            with Horizontal(classes="dialog-actions"):
                yield Button("All projects", id="session-scope")
                yield Button("Retry", id="session-retry")
                yield Button("Cancel", id="session-cancel")
                yield Button("Resume", id="session-resume", variant="primary", disabled=True)

    def on_mount(self):
        self.update_layout()
        self.query_one("#session-retry").display = False
        self.query_one("#session-search").focus()
        self.load_sessions()

    def on_resize(self):
        self.update_layout()

    def update_layout(self):
        # Reserve room for actual rows on laptop/SSH terminals. Fixed chrome
        # formerly consumed almost the entire dialog at 24–26 lines high.
        self.set_class(self.app.size.height < 32, "compact")
        self.set_class(self.app.size.height < 24, "short")

    @work(exclusive=True, group="session-list")
    async def load_sessions(self):
        self.fetching = True
        self.load_error = ""
        self.query_one("#session-retry").display = False
        self.refresh_list()
        cursor = None
        seen_cursors = set()
        try:
            while True:
                result = await self.server.request(
                    "thread/list",
                    {
                        "limit": 100,
                        "sortKey": "updated_at",
                        "modelProviders": [],
                        **({"cursor": cursor} if cursor else {}),
                    },
                )
                for thread in result.get("data", []):
                    self.threads[thread["id"]] = thread
                self.refresh_list()
                cursor = result.get("nextCursor")
                if not cursor:
                    break
                if cursor in seen_cursors:
                    raise ValueError("Codex returned a repeated pagination cursor")
                seen_cursors.add(cursor)
        except Exception as exc:
            self.load_error = str(exc)
        finally:
            if self.is_attached:
                self.fetching = False
                self.query_one("#session-retry").display = bool(self.load_error)
                self.refresh_list()

    def refresh_list(self):
        options = self.query_one("#session-list", OptionList)
        previous = (
            options.get_option_at_index(options.highlighted).id
            if options.highlighted is not None and options.option_count
            else None
        )
        query = self.query_one("#session-search", Input).value.casefold().split()
        matches = []
        for thread in self.threads.values():
            if self.workspace_only and Path(thread.get("cwd", "")) != Path(self.cwd):
                continue
            searchable = " ".join(
                str(thread.get(field) or "") for field in ("name", "preview", "cwd", "id")
            ).casefold()
            if all(term in searchable for term in query):
                matches.append(thread)
        options.clear_options()
        options.add_options(Option(session_label(t, self.current_id), id=t["id"]) for t in matches)
        if matches:
            ids = [t["id"] for t in matches]
            options.highlighted = ids.index(previous) if previous in ids else 0
        self.query_one("#session-resume", Button).disabled = not matches
        status = f"{len(matches)} matching · {len(self.threads)} loaded"
        if self.fetching:
            status += " · Loading older conversations…"
        elif self.load_error:
            status += f" · Could not load all sessions: {self.load_error}"
        elif not matches:
            status = "No matching conversations" if self.threads else "No saved conversations"
        self.query_one("#session-count", Static).update(status)
        self.update_preview()

    @on(Input.Changed, "#session-search")
    def search_changed(self):
        self.refresh_list()

    @on(OptionList.OptionHighlighted, "#session-list")
    def update_preview(self):
        options = self.query_one("#session-list", OptionList)
        preview = "↑/↓ choose · Enter resumes · Esc cancels"
        if options.highlighted is not None and options.option_count:
            key = options.get_option_at_index(options.highlighted).id
            thread = self.threads[key]
            preview = display_text(thread.get("preview") or thread.get("name") or "")
        self.query_one("#session-preview", Static).update(preview)

    def on_key(self, event):
        if self.focused is self.query_one("#session-search") and event.key in {"up", "down"}:
            event.stop()
            options = self.query_one("#session-list", OptionList)
            if event.key == "up":
                options.action_cursor_up()
            else:
                options.action_cursor_down()

    @on(Input.Submitted, "#session-search")
    @on(Button.Pressed, "#session-resume")
    @on(OptionList.OptionSelected, "#session-list")
    def choose(self):
        options = self.query_one("#session-list", OptionList)
        if options.highlighted is not None and options.option_count:
            self.dismiss(options.get_option_at_index(options.highlighted).id)

    @on(Button.Pressed, "#session-scope")
    def toggle_scope(self):
        self.workspace_only = not self.workspace_only
        self.query_one("#session-scope", Button).label = (
            "This project" if self.workspace_only else "All projects"
        )
        self.refresh_list()

    @on(Button.Pressed, "#session-retry")
    def retry(self):
        self.load_sessions()

    @on(Button.Pressed, "#session-cancel")
    def action_cancel(self):
        self.dismiss(None)
