"""User-owned appearance and behavior; no edits to Codex configuration."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pygments.styles import get_style_by_name
from rich.style import Style
from textual.color import Color

PALETTES = {
    "prism": dict(
        background="#10141c",
        surface="#171d28",
        panel="#1d2533",
        foreground="#dce4f2",
        muted="#8c9cb5",
        accent="#72d5ce",
        reasoning="#c4a7e7",
        command="#e8c07d",
        output="#99b7d7",
        assistant="#8bd5ad",
        user="#8aadf4",
        error="#f28b96",
    ),
    "ember": dict(
        background="#1c1715",
        surface="#251f1b",
        panel="#302720",
        foreground="#eadac9",
        muted="#aa9684",
        accent="#e6a66a",
        reasoning="#d2a4b6",
        command="#e5c179",
        output="#a4b8be",
        assistant="#b9c68a",
        user="#a0bcd4",
        error="#ea8c80",
    ),
    "daylight": dict(
        background="#f4f2ee",
        surface="#ffffff",
        panel="#e8e5df",
        foreground="#283348",
        muted="#626b7c",
        accent="#006e78",
        reasoning="#774598",
        command="#895912",
        output="#376589",
        assistant="#237249",
        user="#345da8",
        error="#b93447",
    ),
}

DEFAULT_CONFIG = """# Codex Prism — edit and press Ctrl+R to reload.
[appearance]
theme = "prism"                  # prism, ember, daylight
syntax_theme = "monokai"         # any Pygments theme
line_numbers = true
wrap = true
show_sidebar = true
output_preview_lines = 4
page_lines = 160                 # rendering pages; stored output is never clipped
reasoning = "both"               # both, content, summary

# Override any palette key: background, surface, panel, foreground, muted,
# accent, reasoning, command, output, assistant, user, error.
[colors]
# reasoning = "#c4a7e7"
# command = "#e8c07d"

# Pygments token styles: Token.Name, Token.Literal.String, etc.
[syntax]
# "Token.Name.Builtin" = "bold #72d5ce"
# "Token.Literal.String" = "#a8d49a"

[keys]
next = "j"
previous = "k"
input = "i"
search = "slash"
toggle_output = "o"
expand_all = "shift+o"
copy_command = "y"
copy_output = "shift+y"
follow = "f"

[behavior]
record = true
compress_recordings = true
# Additional Textual CSS, resolved relative to this config file:
# css = "custom.tcss"
"""


def config_path() -> Path:
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "codex-prism/config.toml"
    )


def state_path() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "codex-prism"


@dataclass
class Settings:
    theme: str = "prism"
    syntax_theme: str = "monokai"
    line_numbers: bool = True
    wrap: bool = True
    show_sidebar: bool = True
    output_preview_lines: int = 4
    page_lines: int = 160
    reasoning: str = "both"
    colors: dict[str, str] = field(default_factory=dict)
    syntax: dict[str, str] = field(default_factory=dict)
    keys: dict[str, str] = field(
        default_factory=lambda: dict(
            next="j",
            previous="k",
            input="i",
            search="slash",
            toggle_output="o",
            expand_all="shift+o",
            copy_command="y",
            copy_output="shift+y",
            follow="f",
        )
    )
    record: bool = True
    compress_recordings: bool = True
    css: Path | None = None
    path: Path | None = None

    @property
    def palette(self) -> dict[str, str]:
        return PALETTES[self.theme] | self.colors

    @classmethod
    def load(cls, path: Path | None = None) -> Settings:
        explicit = path is not None
        path = (path or config_path()).expanduser()
        obj = cls(path=path)
        if not path.exists():
            if explicit:
                raise ValueError(f"Config does not exist: {path}")
            return obj
        with path.open("rb") as stream:
            data = tomllib.load(stream)
        if not all(isinstance(v, dict) for v in data.values()):
            raise ValueError("Config sections must be TOML tables")
        allowed = {"appearance", "colors", "syntax", "keys", "behavior"}
        if extra := data.keys() - allowed:
            raise ValueError(f"Unknown config sections: {', '.join(extra)}")
        for section, names in {
            "appearance": {
                "theme",
                "syntax_theme",
                "line_numbers",
                "wrap",
                "show_sidebar",
                "output_preview_lines",
                "page_lines",
                "reasoning",
            },
            "behavior": {"record", "compress_recordings", "css"},
        }.items():
            for key, value in data.get(section, {}).items():
                if key not in names:
                    raise ValueError(f"Unknown {section} option: {key}")
                if key == "css":
                    obj.css = (path.parent / value).resolve()
                else:
                    old = getattr(obj, key)
                    if type(value) is not type(old):
                        raise ValueError(f"{section}.{key} must be {type(old).__name__}")
                    setattr(obj, key, value)
        for section in ("colors", "syntax", "keys"):
            values = data.get(section, {})
            if not isinstance(values, dict) or not all(isinstance(v, str) for v in values.values()):
                raise ValueError(f"{section} must be a table of strings")
            if section == "keys" and (extra := values.keys() - obj.keys.keys()):
                raise ValueError(f"Unknown key actions: {', '.join(extra)}")
            getattr(obj, section).update(values)
        if obj.theme not in PALETTES:
            raise ValueError(f"Unknown theme: {obj.theme}")
        if obj.reasoning not in {"both", "content", "summary"}:
            raise ValueError("reasoning must be both, content, or summary")
        if not 1 <= obj.output_preview_lines <= 50 or not 20 <= obj.page_lines <= 2000:
            raise ValueError("output_preview_lines must be 1–50; page_lines must be 20–2000")
        if unknown := obj.colors.keys() - PALETTES[obj.theme].keys():
            raise ValueError(f"Unknown colors: {', '.join(unknown)}")
        for value in obj.colors.values():
            Color.parse(value)
        for value in obj.syntax.values():
            Style.parse(value)
        get_style_by_name(obj.syntax_theme)
        if obj.syntax:
            from pygments.token import string_to_tokentype

            base = get_style_by_name(obj.syntax_theme)
            type(
                "ValidatedStyle",
                (base,),
                {
                    "styles": base.styles
                    | {string_to_tokentype(k): v for k, v in obj.syntax.items()}
                },
            )
        if obj.css and not obj.css.is_file():
            raise ValueError(f"CSS file does not exist: {obj.css}")
        return obj
