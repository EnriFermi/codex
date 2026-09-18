"""Syntax rendering that does not interpret terminal control sequences."""

from __future__ import annotations

import re
from functools import lru_cache

from pygments.lexer import RegexLexer
from pygments.lexers.shell import BashLexer
from pygments.styles import get_style_by_name
from pygments.token import (
    Generic,
    Name,
    Number,
    Punctuation,
    string_to_tokentype,
)
from pygments.token import (
    Text as TokenText,
)
from rich.syntax import PygmentsSyntaxTheme, Syntax
from rich.text import Text

from .config import Settings
from .math_rendering import MathMarkdown

# OSC (including clipboard), CSI, and other terminal control sequences are data.
ESCAPES = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[@-_]")


class PrismShellLexer(BashLexer):
    """Keep shell quoting intact, while distinguishing flags and paths."""

    def get_tokens_unprocessed(self, text, stack=("root",)):
        expect_command = True
        for index, token, value in super().get_tokens_unprocessed(text, stack):
            if token in TokenText.Whitespace and "\n" in value:
                expect_command = True
            elif token in Punctuation and any(c in value for c in "|;&"):
                expect_command = True
            elif token is TokenText:
                if value.startswith("-") and len(value) > 1:
                    token = Name.Attribute
                elif expect_command:
                    token = Name.Function
                    expect_command = False
                elif "/" in value or re.search(r"\.[a-zA-Z]{1,6}$", value):
                    token = Name.Namespace
            yield index, token, value


class PrismLogLexer(RegexLexer):
    tokens = {
        "root": [
            (r"\b(?:ERROR|FAILED|FAIL|FATAL|Exception|Traceback)\b", Generic.Deleted),
            (r"\b(?:PASSED|PASS|SUCCESS|OK)\b", Generic.Inserted),
            (r"\b(?:WARNING|WARN|SKIPPED|SKIP)\b", Generic.Emph),
            (r"(?:[\w.-]+/)+[\w.-]+(?::\d+)?", Name.Namespace),
            (r"\b\d+(?:\.\d+)?(?:ms|s|%|MiB|KiB)?\b", Number),
            (r"[^\w\n]+|\w+|\n", TokenText),
        ]
    }


def display_text(value: str) -> str:
    value = ESCAPES.sub("", value)
    return "".join(
        c if c in "\n\t" or ord(c) >= 32 and ord(c) != 127 else f"\\x{ord(c):02x}" for c in value
    )


@lru_cache(maxsize=32)
def syntax_style(name: str, overrides: tuple[tuple[str, str], ...]):
    base = get_style_by_name(name)
    if not overrides:
        return PygmentsSyntaxTheme(base)
    styles = dict(base.styles)
    styles.update({string_to_tokentype(k): v for k, v in overrides})
    return PygmentsSyntaxTheme(type("PrismStyle", (base,), {"styles": styles}))


def code(value: str, language: str, settings: Settings, *, start_line: int = 1) -> Syntax:
    semantic = {
        "Token.Name.Function": "bold " + settings.palette["accent"],
        "Token.Name.Attribute": settings.palette["reasoning"],
        "Token.Name.Namespace": settings.palette["output"],
    } | settings.syntax
    return Syntax(
        display_text(value),
        PrismShellLexer()
        if language == "bash"
        else PrismLogLexer()
        if language == "text"
        else language,
        theme=syntax_style(settings.syntax_theme, tuple(sorted(semantic.items()))),
        line_numbers=settings.line_numbers,
        start_line=start_line,
        word_wrap=settings.wrap,
        background_color=settings.palette["surface"],
        padding=(0, 1),
    )


def prose(value: str, settings: Settings):
    return (
        MathMarkdown(
            display_text(value),
            code_theme=settings.syntax_theme,
            math_style=settings.palette["reasoning"],
        )
        if value
        else Text("Waiting for content…", style=settings.palette["muted"])
    )


def output_language(value: str) -> str:
    stripped = value.lstrip()
    if stripped.startswith(("{", "[")):
        try:
            import json

            json.loads(value)
            return "json"
        except ValueError:
            pass
    if stripped.startswith(("diff --git", "--- a/")):
        return "diff"
    if "Traceback (most recent call last)" in value:
        return "pytb"
    return "text"
