"""Keep Rich formatting while exposing actual displayed text to mouse selection."""

from rich.syntax import Syntax
from rich.text import Text
from textual.widgets import Static


def render_text(console, renderable, width: int) -> Text:
    result = Text(no_wrap=True, overflow="crop")
    for segment in console.render(renderable, console.options.update(width=max(1, width))):
        if not segment.control:
            result.append(segment.text, segment.style)
    # Rich ends blocks with a newline; the widget supplies vertical spacing.
    result.rstrip()
    return result


class SelectableText(Static):
    ALLOW_SELECT = True

    def __init__(self, value="", **kwargs):
        super().__init__("", **kwargs)
        self.rich_value = value
        self._text_cache = None

    def update(self, content="", *, layout=True):
        self.rich_value = content
        self._text_cache = None
        self.refresh(layout=layout)

    def render(self):
        return self.render_at_width(max(1, self.content_size.width))

    def render_at_width(self, width):
        if isinstance(self.rich_value, Text):
            return self.rich_value
        if isinstance(self.rich_value, str):
            return Text(self.rich_value)
        if isinstance(self.rich_value, Syntax) and not self.rich_value.word_wrap:
            width = max(
                width,
                self.rich_value.__rich_measure__(
                    self.app.console, self.app.console.options
                ).maximum,
            )
        if self._text_cache is None or self._text_cache[0] != width:
            self._text_cache = (width, render_text(self.app.console, self.rich_value, width))
        return self._text_cache[1]

    def get_content_width(self, container, viewport):
        if isinstance(self.rich_value, Syntax) and not self.rich_value.word_wrap:
            return self.rich_value.__rich_measure__(
                self.app.console, self.app.console.options
            ).maximum
        return super().get_content_width(container, viewport)

    def get_content_height(self, container, viewport, width):
        if isinstance(self.rich_value, (str, Text)):
            return super().get_content_height(container, viewport, width)
        return len(self.render_at_width(max(1, width)).plain.splitlines()) or 1
