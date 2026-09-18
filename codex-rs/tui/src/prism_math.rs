//! Conservative TeX-to-Unicode display conversion. Original message/export data stays untouched.

use pulldown_cmark::Event;
use pulldown_cmark::Parser;
use pulldown_cmark::Tag;
use pulldown_cmark::TagEnd;
use std::borrow::Cow;

pub(crate) fn render(input: &str) -> Cow<'_, str> {
    let mut excluded = Vec::new();
    let mut block = None;
    for (event, range) in Parser::new(input).into_offset_iter() {
        match event {
            Event::Code(_) | Event::Html(_) | Event::InlineHtml(_) => excluded.push(range),
            Event::Start(Tag::CodeBlock(_)) | Event::Start(Tag::Link { .. }) => {
                block = Some(range.start);
            }
            Event::End(TagEnd::CodeBlock) | Event::End(TagEnd::Link) => {
                if let Some(start) = block.take() {
                    excluded.push(start..range.end);
                }
            }
            _ => {}
        }
    }
    let mut result = String::new();
    let mut copied = 0;
    let mut pos = 0;
    while pos < input.len() {
        if let Some(range) = excluded.iter().find(|range| range.contains(&pos)) {
            pos = range.end;
            continue;
        }
        let rest = &input[pos..];
        let escaped = input[..pos]
            .chars()
            .rev()
            .take_while(|c| *c == '\\')
            .count()
            % 2
            == 1;
        let delimiter = if escaped {
            None
        } else if rest.starts_with("$$") {
            Some(("$$", "$$", true))
        } else if rest.starts_with("\\[") {
            Some(("\\[", "\\]", true))
        } else if rest.starts_with("\\(") {
            Some(("\\(", "\\)", false))
        } else if rest.starts_with('$') && rest[1..].starts_with(|c: char| !c.is_whitespace()) {
            Some(("$", "$", false))
        } else {
            None
        };
        if let Some((open, close, display)) = delimiter {
            let start = pos + open.len();
            if let Some(offset) = input[start..].find(close) {
                let end = start + offset;
                let after = end + close.len();
                let source = &input[start..end];
                let currency = close == "$"
                    && (source.ends_with(char::is_whitespace)
                        || source.contains('\n')
                        || input[after..].starts_with(|c: char| c.is_ascii_digit()));
                if !currency
                    && source.len() <= 20_000
                    && !excluded.iter().any(|r| r.start < after && r.end > pos)
                    && let Some(math) = latex(source)
                {
                    result.push_str(&input[copied..pos]);
                    if display {
                        result.push_str("\n\n```text\n");
                        result.push_str(&math);
                        result.push_str("\n```\n\n");
                    } else {
                        result.push('`');
                        result.push_str(&math.replace('`', "′"));
                        result.push('`');
                    }
                    copied = after;
                    pos = after;
                    continue;
                }
            }
        }
        let Some(next) = rest.chars().next() else {
            break;
        };
        pos += next.len_utf8();
    }
    if copied == 0 {
        Cow::Borrowed(input)
    } else {
        result.push_str(&input[copied..]);
        Cow::Owned(result)
    }
}

fn latex(source: &str) -> Option<String> {
    let mut parser = Latex {
        rest: source,
        depth: 0,
    };
    let value = parser.sequence()?;
    parser.rest.is_empty().then(|| value.trim().to_string())
}

struct Latex<'a> {
    rest: &'a str,
    depth: usize,
}

impl Latex<'_> {
    fn pop(&mut self) -> Option<char> {
        let c = self.rest.chars().next()?;
        self.rest = &self.rest[c.len_utf8()..];
        Some(c)
    }

    fn sequence(&mut self) -> Option<String> {
        let mut result = String::new();
        while !self.rest.is_empty() && !self.rest.starts_with('}') {
            result.push_str(&self.atom()?);
        }
        Some(result)
    }

    fn argument(&mut self) -> Option<String> {
        self.rest = self.rest.trim_start();
        self.atom()
    }

    fn atom(&mut self) -> Option<String> {
        if self.depth >= 32 {
            return None;
        }
        self.depth += 1;
        let c = self.pop()?;
        let result = match c {
            '{' => {
                let text = self.sequence()?;
                (self.pop()? == '}').then_some(text)
            }
            '^' | '_' => {
                let arg = self.argument()?;
                let from = "0123456789+-=()in";
                let to = if c == '^' {
                    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁱⁿ"
                } else {
                    "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ᵢₙ"
                };
                let mapped: Option<String> = arg
                    .chars()
                    .map(|ch| {
                        from.chars()
                            .position(|candidate| candidate == ch)
                            .and_then(|index| to.chars().nth(index))
                    })
                    .collect();
                Some(mapped.unwrap_or_else(|| {
                    if arg.chars().count() == 1 {
                        format!("{c}{arg}")
                    } else {
                        format!("{c}({arg})")
                    }
                }))
            }
            '\\' => {
                let end = self
                    .rest
                    .find(|ch: char| !ch.is_ascii_alphabetic())
                    .unwrap_or(self.rest.len());
                let command = if end == 0 {
                    self.pop()?.to_string()
                } else {
                    let command = self.rest[..end].to_string();
                    self.rest = &self.rest[end..];
                    command
                };
                match command.as_str() {
                    "frac" | "dfrac" | "tfrac" => {
                        let a = self.argument()?;
                        let b = self.argument()?;
                        let fraction = match (a.as_str(), b.as_str()) {
                            ("1", "2") => Some("½"),
                            ("1", "3") => Some("⅓"),
                            ("2", "3") => Some("⅔"),
                            ("1", "4") => Some("¼"),
                            ("3", "4") => Some("¾"),
                            _ => None,
                        };
                        Some(fraction.map(str::to_string).unwrap_or_else(|| {
                            let group = |text: String| {
                                if text.chars().all(char::is_alphanumeric) {
                                    text
                                } else {
                                    format!("({text})")
                                }
                            };
                            format!("{}/{}", group(a), group(b))
                        }))
                    }
                    "sqrt" => Some(format!("√({})", self.argument()?)),
                    "mathbb" => {
                        let arg = self.argument()?;
                        Some(
                            match arg.as_str() {
                                "R" => "ℝ",
                                "C" => "ℂ",
                                "N" => "ℕ",
                                "Z" => "ℤ",
                                "Q" => "ℚ",
                                "P" => "ℙ",
                                _ => return None,
                            }
                            .into(),
                        )
                    }
                    "text" | "mathrm" | "operatorname" => {
                        self.rest = self.rest.trim_start();
                        if self.pop()? != '{' {
                            return None;
                        }
                        let end = self.rest.find('}')?;
                        let text = self.rest[..end].to_string();
                        if text.contains(['{', '\\']) {
                            return None;
                        }
                        self.rest = &self.rest[end + 1..];
                        Some(text)
                    }
                    "mathbf" | "mathit" | "boldsymbol" => self.argument(),
                    "left" | "right" | "displaystyle" | "limits" => Some(String::new()),
                    "," | ";" | ":" | "quad" | "qquad" | " " => Some(" ".into()),
                    "!" => Some(String::new()),
                    "\\" => Some("\n".into()),
                    "{" | "}" | "%" | "_" | "$" => Some(command),
                    _ => symbol(&command).map(str::to_string),
                }
            }
            '}' | '`' => None,
            '&' => Some("  ".into()),
            _ => Some(c.to_string()),
        };
        self.depth -= 1;
        result
    }
}

fn symbol(command: &str) -> Option<&'static str> {
    Some(match command {
        "alpha" => "α",
        "beta" => "β",
        "gamma" => "γ",
        "delta" => "δ",
        "epsilon" | "varepsilon" => "ε",
        "theta" => "θ",
        "lambda" => "λ",
        "mu" => "μ",
        "nu" => "ν",
        "pi" => "π",
        "rho" => "ρ",
        "sigma" => "σ",
        "tau" => "τ",
        "phi" | "varphi" => "φ",
        "psi" => "ψ",
        "omega" => "ω",
        "Gamma" => "Γ",
        "Delta" => "Δ",
        "Sigma" => "Σ",
        "Omega" => "Ω",
        "int" => "∫",
        "iint" => "∬",
        "oint" => "∮",
        "sum" => "∑",
        "prod" => "∏",
        "infty" => "∞",
        "partial" => "∂",
        "nabla" => "∇",
        "ell" => "ℓ",
        "cdot" => "·",
        "times" => "×",
        "pm" => "±",
        "le" | "leq" => "≤",
        "ge" | "geq" => "≥",
        "ne" | "neq" => "≠",
        "approx" => "≈",
        "equiv" => "≡",
        "in" => "∈",
        "notin" => "∉",
        "subset" => "⊂",
        "subseteq" => "⊆",
        "cup" => "∪",
        "cap" => "∩",
        "emptyset" => "∅",
        "forall" => "∀",
        "exists" => "∃",
        "to" | "rightarrow" => "→",
        "leftarrow" => "←",
        "Rightarrow" => "⇒",
        "Leftrightarrow" | "iff" => "⇔",
        "mapsto" => "↦",
        "ldots" | "dots" => "…",
        "cdots" => "⋯",
        "langle" => "⟨",
        "rangle" => "⟩",
        "vert" | "lvert" | "rvert" => "|",
        "|" | "Vert" | "lVert" | "rVert" => "‖",
        "sin" => "sin",
        "cos" => "cos",
        "log" => "log",
        "ln" => "ln",
        "exp" => "exp",
        "lim" => "lim",
        "sup" => "sup",
        "inf" => "inf",
        "max" => "max",
        "min" => "min",
        _ => return None,
    })
}

#[cfg(test)]
#[path = "prism_math_tests.rs"]
mod tests;
