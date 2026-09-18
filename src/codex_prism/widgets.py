from __future__ import annotations

import math

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, HorizontalScroll, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static, TextArea

from .config import Settings
from .model import Entry, pretty
from .rendering import code, display_text, output_language, prose
from .selectable import SelectableText

ICONS = {
    "reasoning": "◇",
    "command": "$",
    "tool": "⚙",
    "assistant": "◆",
    "commentary": "·",
    "user": "›",
    "file": "±",
    "plan": "☷",
    "error": "!",
    "system": "·",
    "approval": "?",
}
COLORS = {
    "tool": "command",
    "file": "command",
    "plan": "accent",
    "commentary": "assistant",
    "system": "muted",
    "approval": "command",
}


class PagedText(Vertical):
    """Bounded rendering of unbounded source text; copying/export use the source."""

    def __init__(
        self,
        value: str,
        language: str,
        settings: Settings,
        *,
        markdown: bool = False,
        classes: str = "",
    ):
        super().__init__(classes="paged " + classes)
        self.value = value
        self.language = language
        self.settings = settings
        self.markdown = markdown
        self.page = 0

    def compose(self) -> ComposeResult:
        with HorizontalScroll(classes="page-scroll"):
            yield SelectableText(classes="page-body", markup=False)
        with Horizontal(classes="pager"):
            yield Button("← Previous", classes="page-prev")
            yield Static("", classes="page-label", markup=False)
            yield Button("Next →", classes="page-next")

    def on_mount(self):
        self.refresh_text()

    def set_text(self, value: str):
        self.value = value
        if self.is_mounted:
            self.refresh_text()

    def refresh_text(self):
        lines = self.value.splitlines(keepends=True) or [""]
        pages = max(1, math.ceil(len(lines) / self.settings.page_lines))
        self.page = min(self.page, pages - 1)
        start = self.page * self.settings.page_lines
        chunk = "".join(lines[start : start + self.settings.page_lines])
        body = self.query_one(".page-body", Static)
        body.styles.width = "auto" if not self.markdown and not self.settings.wrap else "1fr"
        body.update(
            prose(chunk, self.settings)
            if self.markdown
            else code(chunk, self.language, self.settings, start_line=start + 1)
        )
        self.query_one(".pager").display = pages > 1
        self.query_one(".page-label", Static).update(
            f"Lines {start + 1}–{min(start + self.settings.page_lines, len(lines))} / {len(lines)}  ·  {self.page + 1}/{pages}"
        )
        self.query_one(".page-prev", Button).disabled = self.page == 0
        self.query_one(".page-next", Button).disabled = self.page == pages - 1

    @on(Button.Pressed)
    def turn_page(self, event: Button.Pressed):
        if event.button.has_class("page-prev") or event.button.has_class("page-next"):
            event.stop()
            self.page += -1 if event.button.has_class("page-prev") else 1
            self.refresh_text()


class TraceCard(Vertical):
    class Selected(Message):
        def __init__(self, entry_id: str):
            super().__init__()
            self.entry_id = entry_id

    def __init__(self, entry: Entry, settings: Settings, number: int):
        super().__init__(id=f"card-{number}", classes=f"trace-card kind-{entry.kind}")
        self.entry = entry
        self.settings = settings
        self.number = number
        self.expanded = False
        self.shown_revision = -1

    def compose(self) -> ComposeResult:
        with Horizontal(classes="card-header"):
            yield Static("", classes="card-heading", markup=False)
            yield Button("Copy", classes="copy-entry")
        yield Static("", classes="card-meta", markup=False)
        kind = self.entry.kind
        if kind == "command":
            yield PagedText("", "bash", self.settings, classes="command-body")
        elif kind == "reasoning":
            yield Static(
                "REASONING · CONTENT AS RECEIVED", classes="section-label reasoning-content-label"
            )
            yield PagedText(
                "", "markdown", self.settings, markdown=True, classes="reasoning-content"
            )
            yield Static("REASONING · SUMMARY", classes="section-label reasoning-summary-label")
            yield PagedText(
                "", "markdown", self.settings, markdown=True, classes="reasoning-summary"
            )
        else:
            yield PagedText("", "text", self.settings, markdown=True, classes="message-body")
        if kind in {"command", "tool", "file"}:
            yield Button("", classes="output-toggle")
            yield Static("", classes="output-preview", markup=False)
            yield PagedText("", "text", self.settings, classes="output-body")
            yield Static("", classes="output-notice", markup=False)

    def on_mount(self):
        self.refresh_entry()

    def on_click(self):
        if not self.screen.selections:
            self.post_message(self.Selected(self.entry.id))

    def source_text(self):
        e = self.entry
        if e.kind == "reasoning":
            parts = []
            if e.content_text:
                parts.append("REASONING CONTENT\n" + e.content_text)
            if e.summary_text:
                parts.append("REASONING SUMMARY\n" + e.summary_text)
            return "\n\n".join(parts)
        if e.command:
            return e.command + ("\n\n" + e.output if e.output else "")
        return e.text + ("\n\n" + e.output if e.output else "")

    @on(Button.Pressed, ".copy-entry")
    def copy_entry(self, event: Button.Pressed):
        event.stop()
        self.app.copy_to_clipboard(self.source_text())
        self.app.notify("Full source sent to terminal clipboard · Ctrl+C copies a selection")

    def refresh_entry(self):
        e, s = self.entry, self.settings
        self.set_classes(
            f"trace-card kind-{e.kind}" + (" selected" if self.has_class("selected") else "")
        )
        color = s.palette.get(COLORS.get(e.kind, e.kind), s.palette["muted"])
        heading = Text(f"{ICONS.get(e.kind, '·')}  {e.kind.upper()}  ", style=f"bold {color}")
        heading.append(f"{self.number:03d}", style=s.palette["muted"])
        if e.kind == "tool":
            heading.append(f"  {display_text(e.title)}", style=s.palette["foreground"])
        if e.status == "inProgress":
            heading.append("   ● running", style=s.palette["accent"])
        self.query_one(".card-heading", Static).update(heading)
        meta = []
        if e.cwd:
            meta.append(e.cwd)
        if e.exit_code is not None:
            meta.append(f"exit {e.exit_code}")
        if e.duration_ms is not None:
            meta.append(f"{e.duration_ms / 1000:.2f}s")
        metadata = self.query_one(".card-meta", Static)
        metadata.display = bool(meta)
        metadata.update(
            Text(
                "  ·  ".join(meta), style=s.palette["error"] if e.exit_code else s.palette["muted"]
            )
        )
        self._section(".command-body", e.command)
        if e.kind == "reasoning":
            show_content = s.reasoning in {"content", "both"}
            show_summary = s.reasoning in {"summary", "both"}
            content = e.content_text if show_content else ""
            summary = e.summary_text if show_summary else ""
            if not content and not summary:
                content = (
                    "Waiting for reasoning content…"
                    if e.status == "inProgress"
                    else "No text was supplied for the selected reasoning view."
                )
            self._section(".reasoning-content", content)
            self.query_one(".reasoning-content-label").display = bool(
                e.content_text and show_content
            )
            self._section(".reasoning-summary", summary)
            self.query_one(".reasoning-summary-label").display = bool(summary)
        elif e.kind != "command":
            body = self.query_one(".message-body", PagedText)
            body.markdown = e.kind in {"user", "assistant", "commentary", "plan"}
            body.language = (
                "diff"
                if e.kind == "file"
                else "json"
                if e.kind in {"tool", "system"} and e.text.lstrip().startswith(("{", "["))
                else "text"
            )
            self._section(".message-body", e.text)
        self.refresh_output()
        self.shown_revision = e.revision

    def _section(self, selector: str, value: str):
        if not self.query(selector):
            return
        widget = self.query_one(selector, PagedText)
        widget.display = bool(value)
        widget.set_text(value)

    def refresh_output(self):
        if self.entry.kind not in {"command", "tool", "file"}:
            return
        e, s = self.entry, self.settings
        has_output = bool(e.output)
        button = self.query_one(".output-toggle", Button)
        button.display = has_output or e.kind == "command"
        lines = len(e.output.splitlines())
        size = len(e.output.encode("utf-8"))
        button.label = f"{'▾' if self.expanded else '▸'} OUTPUT   {lines:,} lines · {size:,} bytes   {'collapse' if self.expanded else 'expand'}"
        button.disabled = not has_output
        preview = self.query_one(".output-preview", Static)
        preview.display = has_output and not self.expanded
        snippets = e.output.splitlines()[: s.output_preview_lines]
        preview.update(Text(display_text("\n".join(snippets)), style=s.palette["output"]))
        output = self.query_one(".output-body", PagedText)
        output.display = has_output and self.expanded
        if self.expanded:
            output.language = output_language(e.output)
            output.set_text(e.output)
        notice = self.query_one(".output-notice", Static)
        notice.display = e.upstream_truncated or (
            has_output and not self.expanded and lines > s.output_preview_lines
        )
        notice.update(
            "Codex reports that this output was truncated upstream. All received text is retained."
            if e.upstream_truncated
            else f"{lines - s.output_preview_lines:,} more lines · press o to open · Y to copy full output"
        )

    @on(Button.Pressed, ".output-toggle")
    def toggle_pressed(self, event: Button.Pressed):
        event.stop()
        self.toggle_output()

    def toggle_output(self):
        self.expanded = not self.expanded
        self.refresh_output()


class Prompt(TextArea):
    BINDINGS = [
        Binding("enter", "submit", "Send"),
        Binding("ctrl+enter", "submit", "Send", show=False),
        Binding("alt+enter", "submit", "Send", show=False),
        Binding("ctrl+j", "submit", "Send", show=False),  # Ctrl+Enter may arrive as LF.
    ]
    completion_open = False

    class Completion(Message):
        def __init__(self, action: str):
            super().__init__()
            self.action = action

    class Submitted(Message):
        def __init__(self, text: str):
            super().__init__()
            self.text = text

    def action_submit(self):
        if self.text.strip():
            self.post_message(self.Submitted(self.text))

    async def _on_key(self, event):
        # TextArea consumes Enter before ordinary bindings. Handle it here;
        # terminals which encode Ctrl+Enter as Enter can now send too.
        if self.completion_open and event.key in {"up", "down", "tab", "enter", "escape"}:
            event.stop()
            event.prevent_default()
            self.post_message(self.Completion(event.key))
        elif event.key in {"enter", "shift+enter", "ctrl+n"}:
            event.stop()
            event.prevent_default()
            if event.key == "enter":
                self.action_submit()
            else:
                self._replace_via_keyboard("\n", *self.selection)
        # The inherited handler handles typing and bracketed paste as usual.


class DetailScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, title: str, text: str, settings: Settings, language: str = "json"):
        super().__init__()
        self.title_text, self.text, self.settings, self.language = title, text, settings, language

    def compose(self):
        with Vertical(id="dialog"):
            yield Static(self.title_text, classes="dialog-title", markup=False)
            with VerticalScroll():
                yield PagedText(self.text, self.language, self.settings)
            yield Button("Close · Esc", id="close-dialog")

    @on(Button.Pressed, "#close-dialog")
    def close_dialog(self):
        self.dismiss()


class RequestScreen(ModalScreen):
    """Explicit approval / structured user-input; never auto-approves."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(self, request: dict, settings: Settings):
        super().__init__()
        self.request, self.settings = request, settings
        self.method = request["method"]
        self.params = request.get("params", {})
        self.questions = self.params.get("questions", [])

    def compose(self):
        with Vertical(id="dialog"):
            yield Static("CODEX NEEDS YOUR INPUT", classes="dialog-title")
            with VerticalScroll():
                yield Static(self.method, markup=False)
                yield PagedText(pretty(self.params), "json", self.settings)
                for i, question in enumerate(self.questions):
                    yield Static(question.get("question", ""), markup=False)
                    labels = [o.get("label", "") for o in question.get("options") or []]
                    if labels:
                        yield Static("  /  ".join(labels), markup=False)
                    yield Input(
                        placeholder="Type your answer",
                        password=question.get("isSecret", False),
                        id=f"answer-{i}",
                    )
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="request-cancel")
                if self.method.endswith("requestApproval"):
                    yield Button("Decline", id="request-decline")
                    yield Button("Allow once", variant="primary", id="request-accept")
                elif self.questions:
                    yield Button("Send answers", variant="primary", id="request-answers")

    def action_cancel(self):
        if self.questions:
            self.dismiss({"answers": {q["id"]: {"answers": []} for q in self.questions}})
        elif "permissions" in self.method.lower():
            self.dismiss({"permissions": {}, "scope": "turn"})
        elif "elicitation" in self.method.lower():
            self.dismiss({"action": "cancel"})
        else:
            self.dismiss({"decision": "cancel"})

    @on(Button.Pressed)
    def respond(self, event: Button.Pressed):
        id = event.button.id
        if id == "request-cancel":
            self.action_cancel()
        elif id == "request-answers":
            answers = {
                q["id"]: {"answers": [self.query_one(f"#answer-{i}", Input).value]}
                for i, q in enumerate(self.questions)
            }
            self.dismiss({"answers": answers})
        elif id in {"request-accept", "request-decline"}:
            if "permissions" in self.method.lower():
                self.dismiss(
                    {
                        "permissions": self.params.get("permissions", {})
                        if id == "request-accept"
                        else {},
                        "scope": "turn",
                    }
                )
            else:
                self.dismiss({"decision": "accept" if id == "request-accept" else "decline"})
