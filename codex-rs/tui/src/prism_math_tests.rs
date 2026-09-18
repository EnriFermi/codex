use super::*;
use pretty_assertions::assert_eq;

#[test]
fn formulas_render_without_changing_code_currency_or_unknown_tex() {
    for (source, expected) in [
        (r"$B=\mathbb{R}^2$", "`B=ℝ²`"),
        (
            r"\(\int_0^1(t,t^2)\,dt=(\frac12,\frac13)\)",
            "`∫₀¹(t,t²) dt=(½,⅓)`",
        ),
        (
            r"$\int_X\|f(x)\|_B\,d\mu(x)<\infty$",
            "`∫_X‖f(x)‖_B dμ(x)<∞`",
        ),
        (
            r"\[x^{n+1}\leq \frac{a+b}{c+d}\]",
            "\n\n```text\nxⁿ⁺¹≤ (a+b)/(c+d)\n```\n\n",
        ),
        (r"$$\alpha+\beta$$", "\n\n```text\nα+β\n```\n\n"),
        (r"price $5 and $10", "price $5 and $10"),
        (r"`$\alpha$`", r"`$\alpha$`"),
        ("```python\nx='$a$'\n```", "```python\nx='$a$'\n```"),
        (r"\$5 and \$10", r"\$5 and \$10"),
        (r"$\unknown{x}$", r"$\unknown{x}$"),
        (r"$\frac{1}{$", r"$\frac{1}{$"),
        (r"[file](file:///$x$)", r"[file](file:///$x$)"),
    ] {
        assert_eq!(render(source).as_ref(), expected, "{source}");
    }
}

#[test]
fn bochner_display_snapshot() {
    let source = r"For $B=\mathbb{R}^2$, \(\int_0^1(t,t^2)\,dt=(\frac12,\frac13)\).";
    let rewritten = render(source);
    let lines = crate::markdown_render::render_markdown_text(&rewritten);
    insta::assert_snapshot!(
        lines
            .lines
            .iter()
            .map(ToString::to_string)
            .collect::<Vec<_>>()
            .join("\n")
    );
    assert_eq!(latex(r"\text{f_name}"), Some("f_name".into()));
    assert_eq!(latex(r"\input{secrets}"), None);
    assert_eq!(latex(&"{".repeat(100)), None);
}
