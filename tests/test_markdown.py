from rich.console import Console

from codex_prism.app import Prism
from codex_prism.config import Settings
from codex_prism.model import Entry, Trace
from codex_prism.rendering import prose
from codex_prism.selectable import SelectableText, render_text
from codex_prism.storage import export_markdown


def test_markdown_headings_styles_links_lists_tables_and_code():
    source = """# Heading

Some **bold words**, *italic words*, and [a link](https://example.com).

- First item
- Second item

| Name | Value |
| --- | --- |
| alpha | 42 |

```python
print("**literal**")
```
"""
    console = Console(width=90)
    text = render_text(console, prose(source, Settings()), 90)
    assert "Heading" in text.plain and "# Heading" not in text.plain
    assert text.get_style_at_offset(console, text.plain.index("bold words")).bold
    assert text.get_style_at_offset(console, text.plain.index("italic words")).italic
    assert (
        text.get_style_at_offset(console, text.plain.index("a link")).link == "https://example.com"
    )
    assert "First item" in text.plain and "Second item" in text.plain
    assert "alpha" in text.plain and "42" in text.plain and "| --- |" not in text.plain
    assert 'print("**literal**")' in text.plain


async def test_streaming_display_math_reformats_and_copy_keeps_the_source():
    trace = Trace()
    source = "**Integrability** requires:\n\\[\n\\boxed{\\int_X f\\,d\\mu<\\infty.}"
    trace.entries["math-stream"] = Entry(id="math-stream", kind="assistant", text=source)
    app = Prism(Settings(record=False), trace=trace, offline=True)
    async with app.run_test(size=(100, 35)) as pilot:
        card = app.cards["math-stream"]
        body = card.query_one(".message-body .page-body", SelectableText)
        assert r"\boxed{" in body.render().plain  # Incomplete markup stays visible.
        delta = "\n\\]\nThe integral is finite."
        app.incoming(
            {
                "method": "item/agentMessage/delta",
                "params": {"itemId": "math-stream", "delta": delta},
            }
        )
        await app.flush_events()
        await pilot.pause()
        rendered = body.render().plain
        assert "∫_X f dμ<∞." in rendered and "\\" not in rendered
        assert "╭" in rendered and "The integral is finite." in rendered
        assert "**" not in rendered
        await pilot.click(card.query_one(".copy-entry"))
        assert app.clipboard == source + delta
        assert source + delta in export_markdown(trace)
