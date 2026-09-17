"""Local composer commands and discoverable completions."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    text: str
    usage: str
    description: str


COMMANDS = (
    Command("/new", "/new", "Start a new conversation"),
    Command("/resume ", "/resume UUID", "Continue a saved conversation by thread ID"),
    Command("/sessions", "/sessions", "List recent conversations and their IDs"),
    Command("/theme ", "/theme NAME", "Change colors: prism, ember, daylight"),
    Command("/export ", "/export [PATH]", "Save the full trace as Markdown; path is optional"),
    Command("/stop", "/stop", "Interrupt the current turn"),
    Command("/help", "/help", "Show keyboard shortcuts and command help"),
)
THEMES = (
    Command("/theme prism", "/theme prism", "Cool dark palette"),
    Command("/theme ember", "/theme ember", "Warm dark palette"),
    Command("/theme daylight", "/theme daylight", "Light palette"),
)


def suggestions(text: str) -> list[Command]:
    if "\n" in text or not text.startswith("/"):
        return []
    choices = THEMES if text.startswith("/theme ") else COMMANDS
    return [c for c in choices if c.text.startswith(text) and text not in {c.text, c.text.rstrip()}]


def command_help(text: str) -> str:
    if not text.startswith("/") or "\n" in text:
        return "Enter sends · Shift+Enter / Ctrl+N newline · / commands"
    name = text.partition(" ")[0]
    for command in COMMANDS:
        if command.text.rstrip() == name:
            return f"{command.usage} — {command.description}"
    return "No matching command · /help lists available commands"
