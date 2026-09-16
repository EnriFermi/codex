import pytest
from pygments.token import Name, String

from codex_prism.config import DEFAULT_CONFIG, Settings
from codex_prism.rendering import PrismShellLexer, display_text, syntax_style
from codex_prism.storage import private_write


def test_commented_template_and_overrides(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(DEFAULT_CONFIG)
    assert Settings.load(p).theme == "prism"
    p.write_text(
        '[appearance]\ntheme="daylight"\n[colors]\ncommand="#112233"\n[syntax]\n"Token.Name.Attribute"="bold #aabbcc"\n'
    )
    s = Settings.load(p)
    assert s.palette["command"] == "#112233"
    assert syntax_style(s.syntax_theme, tuple(s.syntax.items()))


@pytest.mark.parametrize(
    "config",
    [
        "[appearance]\npage_lines=0",
        '[appearance]\nwrap="false"',
        '[keys]\nmissing="q"',
        '[appearance]\nreasoning="unknown"',
        "[typo]\nx=1",
    ],
)
def test_invalid_config_rejected(tmp_path, config):
    p = tmp_path / "config.toml"
    p.write_text(config)
    with pytest.raises(ValueError):
        Settings.load(p)


def test_shell_flags_do_not_recolor_quoted_strings():
    tokens = list(
        PrismShellLexer().get_tokens_unprocessed("rg --line-number '--literal' src/main.py")
    )
    assert any(t == Name.Attribute and v == "--line-number" for _, t, v in tokens)
    assert any(t in String and "--literal" in v for _, t, v in tokens)
    assert any(t == Name.Namespace and v == "src/main.py" for _, t, v in tokens)


def test_terminal_escape_sequences_are_inert():
    assert display_text("\x1b]52;c;payload\x07hello\x1b[31m!\x1b[0m") == "hello!"
    assert "\x1b" not in display_text("unfinished\x1b]52;c;payload")


def test_export_never_overwrites(tmp_path):
    path = tmp_path / "x.md"
    private_write(path, "original")
    with pytest.raises(FileExistsError):
        private_write(path, "replacement")
    assert path.read_text() == "original"
