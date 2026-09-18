"""Session controls in Prism's UI, backed by confirmed app-server settings."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from rich.text import Text
from textual import on
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, OptionList, Static
from textual.widgets.option_list import Option


@dataclass(frozen=True)
class Choice:
    key: str
    label: str
    description: str


PERMISSIONS = (
    Choice(":read-only", "Read only", "Read files. Ask before editing or accessing the internet."),
    Choice(
        ":workspace",
        "Workspace",
        "Edit workspace files and run commands. Ask for access outside the workspace or to the internet.",
    ),
    Choice(
        ":danger-full-access",
        "Full access",
        "Edit files anywhere and use the internet without approval prompts.",
    ),
)


class ChoiceScreen(ModalScreen):
    """Highlighting never applies a choice; Enter moves to the explicit Apply button."""

    BINDINGS = [("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        current: str,
        choices: list[Choice] | tuple[Choice, ...],
        selected: str | None = None,
    ):
        super().__init__()
        self.heading, self.current, self.choices, self.selected = title, current, choices, selected

    def compose(self):
        with Vertical(id="settings-dialog"):
            yield Static(self.heading, classes="dialog-title", markup=False)
            yield Static(self.current, id="settings-current", markup=False)
            yield OptionList(
                *(Option(Text(c.label), id=c.key) for c in self.choices), id="settings-options"
            )
            yield Static("", id="settings-description", markup=False)
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel · Esc", id="settings-cancel")
                yield Button("Apply", id="settings-apply", variant="primary")

    def on_mount(self):
        options = self.query_one(OptionList)
        options.highlighted = next(
            (i for i, c in enumerate(self.choices) if c.key == self.selected), 0
        )
        options.focus()

    @on(OptionList.OptionHighlighted)
    def highlight(self, event: OptionList.OptionHighlighted):
        self.query_one("#settings-description", Static).update(
            self.choices[event.option_index].description
        )

    @on(OptionList.OptionSelected)
    def select(self, event: OptionList.OptionSelected):
        event.stop()
        self.query_one("#settings-apply", Button).focus()

    @on(Button.Pressed, "#settings-apply")
    def apply_choice(self):
        index = self.query_one(OptionList).highlighted
        if index is not None:
            self.dismiss(self.choices[index].key)

    @on(Button.Pressed, "#settings-cancel")
    def action_cancel(self):
        self.dismiss(None)


class SessionSettings:
    def __init__(self, response: dict):
        self.thread_id = response["thread"]["id"]
        self.values = self.from_response(response)
        self.waiter: asyncio.Future | None = None
        self.lock = asyncio.Lock()

    @staticmethod
    def from_response(response: dict) -> dict:
        fields = (
            "model",
            "modelProvider",
            "cwd",
            "approvalPolicy",
            "approvalsReviewer",
            "activePermissionProfile",
            "serviceTier",
        )
        return {
            **{k: response[k] for k in fields if k in response},
            "sandboxPolicy": response.get("sandbox", {}),
            "effort": response.get("reasoningEffort"),
        }

    def incoming(self, message: dict):
        params = message.get("params", {})
        if params.get("threadId") != self.thread_id:
            return
        if message.get("method") == "thread/settings/updated":
            self.values = params["threadSettings"]
            if self.waiter and not self.waiter.done():
                self.waiter.set_result(None)

    def matches(self, changes: dict) -> bool:
        return all(
            (self.values.get("activePermissionProfile") or {}).get("id") == value
            if key == "permissions"
            else self.values.get(key) == value
            for key, value in changes.items()
        )

    async def apply(self, server, changes: dict, *, timeout: float = 5) -> bool:
        async with self.lock:
            if self.matches(changes):
                return False
            self.waiter = asyncio.get_running_loop().create_future()
            try:
                # The RPC acknowledges queueing only. Wait for the server's
                # applied-settings event before displaying success.
                await server.request(
                    "thread/settings/update", {"threadId": self.thread_id, **changes}
                )
                try:
                    await asyncio.wait_for(asyncio.shield(self.waiter), timeout)
                except asyncio.TimeoutError:
                    # An unchanged update may emit no event. Resume an already
                    # loaded thread without overrides to read its actual state.
                    response = await server.request(
                        "thread/resume", {"threadId": self.thread_id, "excludeTurns": True}
                    )
                    self.values = self.from_response(response)
                if not self.matches(changes):
                    raise ValueError(
                        "Codex did not apply the requested settings. Open /status to inspect the current settings."
                    )
                return True
            finally:
                if not self.waiter.done():
                    self.waiter.cancel()
                self.waiter = None


async def list_models(server) -> list[dict]:
    models, cursor = [], None
    while True:
        page = await server.request(
            "model/list", {"limit": 100, **({"cursor": cursor} if cursor else {})}
        )
        models.extend(m for m in page["data"] if not m.get("hidden"))
        cursor = page.get("nextCursor")
        if not cursor:
            return models
