from io import StringIO

import pytest
from rich.console import Console

from codex_prism.config import Settings
from codex_prism.math_rendering import render_math
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
