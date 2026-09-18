from io import StringIO

import pytest
from rich.console import Console

from codex_prism.config import Settings
from codex_prism.math_rendering import math_parser, outer_box, render_math
from codex_prism.rendering import prose


def plain(source):
    console = Console(file=StringIO(), width=120, color_system=None)
    console.print(prose(source, Settings()))
    return console.file.getvalue()


@pytest.mark.parametrize(
    "opening,closing", [("$", "$"), ("$$", "$$"), (r"\(", r"\)"), (r"\[", r"\]")]
)
def test_math_delimiters_survive_markdown_and_render(opening, closing):
    text = plain(opening + r"\int_0^1(t,t^2)\,dt=\left(\frac12,\frac13\right)" + closing)
    assert "∫₀¹(t,t²) dt=(½,⅓)" in text
    assert r"\frac" not in text and r"\int" not in text


def test_bochner_definition_preserves_norm_and_spaces():
    text = plain(r"""A function is **Bochner integrable** exactly when it is strongly measurable and

\[
\int_X \|f(x)\|_B\,d\mu(x)<\infty.
\]

For \(B=\mathbb{R}^2\), integrate componentwise. The same definition works in $L^2([0,1])$.
""")
    assert "Bochner integrable" in text and "strongly measurable" in text
    assert "∫_X ‖f(x)‖_B dμ(x)<∞." in text
    assert "B=ℝ²" in text and "L²([0,1])" in text


def test_fraction_grouping_and_literal_text():
    assert render_math(r"\frac{1}{\frac{a}{b}}") == "1/(a/b)"
    assert render_math(r"\frac{a+b}{c+d}") == "(a+b)/(c+d)"
    assert render_math(r"\text{file_name}+x^{n+1}") == "file_name+xⁿ⁺¹"
    assert render_math(r"x^{\alpha+\beta}") == "x^{α+β}"
    assert render_math(r"\operatorname{Var}(X)") == "Var(X)"


def test_matrices_and_multiline_environments():
    assert render_math(r"\begin{pmatrix}1&2\\3&4\end{pmatrix}") == "[ 1 2; 3 4 ]"
    text = render_math(r"\begin{aligned}a&=b+c\\d&=e\end{aligned}")
    assert "=b+c\n" in text and "=e" in text
    assert "½" in plain("```math\n\\frac12\n```")


@pytest.mark.parametrize(
    "source",
    [r"\unknown{a}+b", r"\frac{x}{", r"\input{/etc/passwd}", r"\begin{mystery}x\end{mystery}"],
)
def test_unknown_incomplete_or_unsafe_tex_remains_literal(source):
    assert render_math(source) == source
    assert source in plain("$$" + source + "$$")


def test_code_currency_and_escaped_dollars_are_untouched():
    source = r"""Costs $5 and $10; escaped \$x\$.

`\(\frac12\)` and `$x^2$` are source examples.

```latex
\[\frac12\]
```

```python
print('$x^2$')
```
"""
    text = plain(source)
    assert "$5 and $10" in text and "$x$" in text
    assert r"\(\frac12\)" in text
    assert r"\[\frac12\]" in text
    assert "print('$x^2$')" in text
    assert "½" not in text


def test_trailing_prose_and_incomplete_delimiters_preserved():
    assert "Before x² after." in plain(r"Before \[x^2\] after.")
    assert r"\(\frac{a}" in plain(r"Streaming \(\frac{a}")
    assert "**" not in plain(r"**Bold** with \(x^2\)")


def test_boxed_bochner_formula_and_common_math_formatting():
    source = r"""For a strongly measurable function, **integrability** means:
\[
\boxed{\int_\Omega\|f(\omega)\|_B\,d\mu(\omega)<\infty.}
\]
The limit is in the norm of the Banach space.
"""
    text = plain(source)
    assert "∫_Ω‖f(ω)‖_B dμ(ω)<∞." in text
    assert "╭" in text and "╰" in text  # Box survives as a terminal frame.
    assert "\\" not in text and "**" not in text
    assert render_math(r"\displaystyle\boxed{\frac12}") == "½"
    assert render_math(r"\boldsymbol{\alpha}+\bm{x}") == "α+x"
    assert outer_box(r"\boxed{\frac{a}{b}}")
    assert not outer_box(r"\boxed{x}+\boxed{y}")
    assert not outer_box(r"\boxed{x")


@pytest.mark.parametrize("opening,closing", [(r"\[", r"\]"), ("$$", "$$")])
@pytest.mark.parametrize("prefix", ["", "> ", "  "])
def test_display_math_interrupts_prose_without_blank_lines(opening, closing, prefix):
    before = "- Before" if prefix == "  " else prefix + "Before"
    source = "\n".join(
        [before, prefix + opening, prefix + r"\frac12", prefix + closing, prefix + "After"]
    )
    tokens = math_parser().parse(source)
    blocks = [t for t in tokens if t.type == "math_block"]
    assert len(blocks) == 1
    assert render_math(blocks[0].content) == "½"
    assert [t.content for t in tokens if t.type == "inline"] == ["Before", "After"]
    text = plain(source)
    assert "Before" in text and "After" in text and "½" in text
    assert not any("Before" in line and "½" in line for line in text.splitlines())


def test_math_in_indented_and_fenced_code_is_not_rendered():
    for source in ["    \\[\\boxed{\\frac12}\\]", "```latex\n\\[\\boxed{\\frac12}\\]\n```"]:
        text = plain(source)
        assert r"\boxed{\frac12}" in text and "½" not in text
