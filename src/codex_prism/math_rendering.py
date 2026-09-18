"""Markdown math to terminal Unicode, without evaluating TeX or changing source.

Recognize math before Markdown's escape rule can eat \\( / \\[ delimiters.
Unsupported or incomplete TeX stays literal rather than silently losing macros.
"""

from __future__ import annotations

import re
from functools import lru_cache

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from pylatexenc.latex2text import LatexNodes2Text
from pylatexenc.latexwalker import LatexWalker, LatexWalkerError, get_default_latex_context_db
from pylatexenc.macrospec import MacroSpec, MacroStandardArgsParser, SpecialsSpec
from rich.markdown import Markdown, MarkdownElement
from rich.padding import Padding
from rich.panel import Panel
from rich.text import Text

SUPERSCRIPT = dict(zip("0123456789+-=()in", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁱⁿ"))
SUBSCRIPT = dict(zip("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"))
FRACTIONS = {("1", "2"): "½", ("1", "3"): "⅓", ("2", "3"): "⅔", ("1", "4"): "¼", ("3", "4"): "¾"}
SYMBOLS = {
    "|": "‖",
    "lVert": "‖",
    "rVert": "‖",
    "Vert": "‖",
    "lvert": "|",
    "rvert": "|",
    "not": "¬",
    "\\": "\n",
    "left": "",
    "right": "",
    "big": "",
    "Big": "",
    "bigl": "",
    "bigr": "",
    "Bigl": "",
    "Bigr": "",
    "displaystyle": "",
    "textstyle": "",
    "scriptstyle": "",
    "scriptscriptstyle": "",
    "mathstrut": "",
}
WRAPPERS = {"boxed", "fbox", "bm", "boldsymbol"}
FORBIDDEN = {"input", "include", "includegraphics", "write", "openout", "read", "def", "newcommand"}


class MathText(LatexNodes2Text):
    def macro_node_to_text(self, node):
        name = node.macroname
        if name in SYMBOLS:
            return SYMBOLS[name]
        if name in WRAPPERS:
            return self._groupnodecontents_to_text(node.nodeargd.argnlist[-1])
        if name in {"frac", "dfrac", "tfrac"}:
            args = node.nodeargd.argnlist
            a, b = (self._groupnodecontents_to_text(arg).strip() for arg in args[-2:])
            if (a, b) in FRACTIONS:
                return FRACTIONS[a, b]

            def grouped(value):
                return value if re.fullmatch(r"[\w⁰¹²³⁴⁵⁶⁷⁸⁹]+", value) else f"({value})"

            return f"{grouped(a)}/{grouped(b)}"
        if name in {"text", "textrm", "textnormal", "operatorname"}:
            # An underscore inside \text{file_name} is text, not a subscript.
            arg = node.nodeargd.argnlist[-1]
            previous = getattr(self, "literal_scripts", False)
            self.literal_scripts = True
            try:
                return self._groupnodecontents_to_text(arg)
            finally:
                self.literal_scripts = previous
        if name in FORBIDDEN or self.latex_context.get_macro_spec(name) is None:
            raise ValueError(f"Unsupported math macro: {name}")
        return super().macro_node_to_text(node)

    def specials_node_to_text(self, node):
        if node.specials_chars in {"^", "_"}:
            if getattr(self, "literal_scripts", False):
                return node.latex_verbatim()
            value = self._groupnodecontents_to_text(node.nodeargd.argnlist[0]).strip()
            table = SUPERSCRIPT if node.specials_chars == "^" else SUBSCRIPT
            if value and all(char in table for char in value):
                return "".join(table[char] for char in value)
            # Braces preserve grouping when Unicode has no matching glyphs.
            return (
                f"{node.specials_chars}{value}"
                if len(value) == 1
                else f"{node.specials_chars}{{{value}}}"
            )
        return super().specials_node_to_text(node)

    def environment_node_to_text(self, node):
        if node.environmentname in {
            "align",
            "align*",
            "aligned",
            "split",
            "gather",
            "gather*",
            "gathered",
            "equation",
            "equation*",
            "cases",
        }:
            text = self.nodelist_to_text(node.nodelist).strip()
            return "{ " + text + " }" if node.environmentname == "cases" else text
        if self.latex_context.get_environment_spec(node.environmentname) is None:
            raise ValueError(f"Unsupported math environment: {node.environmentname}")
        return super().environment_node_to_text(node)


@lru_cache(maxsize=1)
def math_context():
    context = get_default_latex_context_db()
    context.add_context_category(
        "prism-math",
        prepend=True,
        specials=[SpecialsSpec(char, MacroStandardArgsParser("{")) for char in ("^", "_")],
        macros=[
            MacroSpec("operatorname", "*{"),
            MacroSpec("dfrac", "{{"),
            MacroSpec("tfrac", "{{"),
            *(MacroSpec(name, "{") for name in WRAPPERS),
            *(
                MacroSpec(name, "")
                for name in SYMBOLS
                if name.endswith("style") or name == "mathstrut"
            ),
        ],
    )
    return context


@lru_cache(maxsize=512)
def render_math(source: str) -> str:
    if len(source) > 20000:
        return source
    # A malformed/deep expression must not crash the UI while streaming.
    depth = 0
    for char in source:
        depth += (char == "{") - (char == "}")
        if depth > 64:
            return source
    try:
        expression = re.sub(r"\\(?:left|right)\s*\.", "", source)
        nodes, _, _ = LatexWalker(
            expression, latex_context=math_context(), tolerant_parsing=False
        ).get_latex_nodes()
        rendered = MathText(math_mode="text").nodelist_to_text(nodes).strip()
        return rendered.replace("¬∈", "∉").replace("¬=", "≠") or source
    except (LatexWalkerError, ValueError, TypeError, IndexError, RecursionError):
        return source


def bracket_inline(state, silent):
    opening = state.src[state.pos : state.pos + 2]
    if opening not in {r"\(", r"\["}:
        return False
    closing = r"\)" if opening == r"\(" else r"\]"
    end = state.src.find(closing, state.pos + 2)
    if not silent:
        token = state.push("math_inline" if end >= 0 else "text", "", 0)
        token.content = state.src[state.pos + 2 : end] if end >= 0 else state.src[state.pos :]
    state.pos = end + 2 if end >= 0 else state.posMax
    return True


def display_math_block(state, start_line, end_line, silent):
    if state.is_code_block(start_line):
        return False
    start = state.bMarks[start_line] + state.tShift[start_line]
    opening = state.src[start : start + 2]
    if opening not in {r"\[", "$$"}:
        return False
    closing = r"\]" if opening == r"\[" else "$$"
    end = state.src.find(closing, start + 2)
    if end < 0 or end >= state.bMarks[end_line]:
        return False
    last_line = start_line
    while last_line + 1 < end_line and state.bMarks[last_line + 1] <= end:
        last_line += 1
    if state.src[end + 2 : state.eMarks[last_line]].strip():
        return False  # Preserve trailing prose through the inline rule.
    if silent:
        return True
    token = state.push("math_block", "", 0)
    # getLines removes quote/list prefixes using the block parser's offsets.
    content = state.getLines(start_line, last_line + 1, state.blkIndent, False).strip()
    token.content = content[2:-2]
    token.map = [start_line, last_line + 1]
    state.line = last_line + 1
    return True


@lru_cache(maxsize=1)
def math_parser():
    parser = MarkdownIt().enable("strikethrough").enable("table")
    parser.use(
        dollarmath_plugin,
        allow_labels=False,
        allow_space=False,
        allow_digits=False,
        double_inline=True,
    )
    # Display math may interrupt prose, just like a fenced code block. Without
    # these alternatives, a formula immediately after a sentence is swallowed
    # into its paragraph and all line breaks collapse to spaces.
    parser.block.ruler.at(
        "math_block", display_math_block, {"alt": ["paragraph", "reference", "blockquote", "list"]}
    )
    parser.inline.ruler.before("escape", "prism_bracket_math", bracket_inline)
    return parser


def outer_box(source: str) -> bool:
    """Only frame an equation when its entire content has a box wrapper."""
    source = source.strip()
    opening = re.match(r"\\(?:boxed|fbox)\s*\{", source)
    if not opening:
        return False
    depth = 1
    escaped = False
    for i in range(opening.end(), len(source)):
        if escaped:
            escaped = False
            continue
        if source[i] == "\\":
            escaped = True
            continue
        depth += (source[i] == "{") - (source[i] == "}")
        if depth == 0:
            return i == len(source) - 1
    return False


class MathBlock(MarkdownElement):
    @classmethod
    def create(cls, markdown, token):
        element = cls()
        element.text = Text(render_math(token.content), style=markdown.math_style)
        element.boxed = outer_box(token.content)
        element.math_style = markdown.math_style
        return element

    def __rich_console__(self, console, options):
        yield Padding(
            Panel.fit(self.text, border_style=self.math_style) if self.boxed else self.text,
            (0, 2),
        )


class MathMarkdown(Markdown):
    elements = {**Markdown.elements, "math_block": MathBlock}

    def __init__(self, source: str, *, code_theme: str, math_style: str):
        super().__init__(source, code_theme=code_theme)
        self.math_style = math_style
        self.parsed = math_parser().parse(source)
        self._convert(self.parsed)

    def _convert(self, tokens):
        for token in tokens:
            if token.type in {"math_inline", "math_inline_double"}:
                token.type, token.tag = "text", ""
                token.content = render_math(token.content)
            elif token.type == "fence" and token.info.strip() == "math":
                token.type, token.tag = "math_block", ""
            if token.children:
                self._convert(token.children)
