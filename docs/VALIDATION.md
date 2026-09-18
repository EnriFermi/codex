# Validation

## Session chooser, math and text selection — 2026-09-18

**64 offline tests pass on Python 3.11 and 3.12**, with Textual 8.2.8 and pylatexenc 2.11. New coverage includes both `/resume` and `/sessions`, searching a later page by preview, resuming its paginated history, cancellation, retry after a failed list request, empty search results and preserving the current trace after a history error.

Math fixtures cover the Bochner example, four delimiter forms, fenced `math`, norms, nested fraction grouping, super/subscripts, matrices and multiline expressions. Code examples, currency, escaped dollars, unknown commands and incomplete streamed TeX remain literal. Source text is retained independently of display. This is Unicode terminal rendering, not complete graphical LaTeX typesetting.

Mouse drag selects rendered Markdown and Ctrl+C copies it even when focus was in the composer. Tests also cover copying inside the composer, retaining full source through Copy, buffering UI updates while a selection exists, and the horizontally scrollable tail of unwrapped code. Clipboard checks verify the app-side text; acceptance by an actual user's terminal/system clipboard depends on OSC 52 support.

A read-only check against installed **Codex 0.153.3** returned two distinct pages through `thread/list` with `modelProviders: []`, including the title/preview/directory/time metadata used by the chooser. No model turn was started and no real session names were committed. The reviewed protocol baseline now also covers `ThreadListParams.cursor` and `.modelProviders`; its engine version remains 0.153.3.

Synthetic math and session-picker screens were rendered and inspected. The math PNG uses DejaVu Sans Mono to include the mathematical glyphs; the application's actual font is controlled by the user's terminal.

## Maintenance and input fixes — 2026-09-17

The expanded offline suite passes on Python 3.11 and 3.12. It covers ordinary Enter, Ctrl+Enter, LF/Ctrl+J, Alt+Enter and the Send button through the fake app-server; multiline input and paste; command filtering, keyboard/mouse completion, argument hints, Escape, and an 80 × 24 terminal. A separate Linux PTY check sent actual CR, LF and CSI-u Ctrl+Enter bytes through the real terminal driver: all three completed a fake-server turn and exited cleanly. No model was called in these checks.

The official complete **Codex 0.154.0 Linux x86_64 musl** package passed SHA-256 verification, consumed-field structural comparison against 0.153.3 and app-server initialization with a temporary profile. Its checked shapes were identical. Full model behavior on 0.154.0 remains untested; the working installation remains 0.153.3.

The updater tests reject prereleases, missing packages/digests, unexpected URLs, downgrades, consumed-type/enum changes and newly required fields. They verify credential isolation and removal of stale successful reports. The GitHub workflow passes local actionlint validation; executing it and creating PRs remotely depend on the repository's Actions settings. The private repository's Actions status cannot be read with the available SSH-only authentication.

## Initial release — 2026-09-16

Checked on Linux, Python 3.12.13, Textual 1.0.0, and **Codex CLI 0.153.3**. Test inputs and screenshots are synthetic. Real session recordings remain in ignored `private/`; no actual reasoning text, credentials, or user conversations are checked in.

## Measured integration checks

| Check | Result | Scope |
| --- | --- | --- |
| Installed CLI `--doctor` | Passed | Actual app-server startup, initialize/initialized handshake, clean child shutdown; no model call |
| Live model → shell command → answer | Passed | One harmless `printf`; both output markers and final reply received, successful turn completion |
| Long output | Passed | One harmless command generated 2,000 distinct lines; all 32,000 bytes reached the client despite a requested smaller tool-result token limit |
| Persistent history | Passed | Created a dedicated smoke-test conversation, completed one turn, restarted app-server, resumed and loaded full paginated history; reply marker present. Test conversation was then archived. |
| Protocol contract | Passed | Installed-version schema contains the required handshake, thread/turn, approval, output, and separate reasoning-stream fields |

The live model tests used the inherited configured model, `gpt-6-astra`. A short smoke turn produced **27 characters of reasoning summary and no reasoning content**. This confirms that summary and content availability must be treated separately. Raw-content handling is covered by deterministic event tests and the installed schema; it was not observed from the live provider in that short test.

The long-output test received output through the completed command item, with zero output-delta notifications. Therefore the measurement establishes full capture for that command, not unrestricted streaming behavior for every tool. Streamed output handling is tested separately with controlled protocol events.

## Automated checks

`uv run pytest -q` covers:

- Full multiline command preservation and reconstruction from output chunks, including a 100 KB output with a shortened completion snapshot.
- Separate summary/content streams, indexed parts and snapshot/delta deduplication.
- Unicode gzip recording/replay, private permissions, safe Markdown fences, and export without overwriting files.
- JSON-RPC correlation, concurrent requests, frames above 64 KB, server requests, explicit errors, timeout cleanup and EOF.
- Shell flags versus quoted strings; terminal escape sequences rendered as inert text.
- Config validation, theme overrides and reloading changed keybindings.
- TUI navigation, search inside collapsed output, folding, theme switching, full export, paged 10,000-line output and terminal resize.
- Explicit approval selection, questions keyed by their IDs, and cancellation granting no permissions.
- A complete UI → subprocess → command/output → completed answer round trip using a controlled fake app-server; no model credentials needed for the test suite.

The initial release count and status are recorded in [validation-results.json](validation-results.json). Lint, formatting, build and installed CLI checks are run separately. The CI workflow covers Python 3.11 and 3.12; remote run status has not been independently verified.

## Visual checks

The terminal UI was rendered at 132 × 48 cells, with command, folded output and expanded-output views. Screenshots were inspected after enabling color in the test process (the agent execution environment sets `NO_COLOR`). PNG previews use JetBrains Mono for rendering; the app itself uses your terminal's font.

## Limits

- No claim of unavailable server-side reasoning or reconstruction of bytes the server never sends.
- macOS/Windows terminal behavior and OSC 52 clipboard integration were not exercised on physical terminals; Linux headless TUI and a PTY launch are covered locally.
- Histories currently retain card widgets in memory. Very large histories are not viewport-virtualized.
- Image events are represented as metadata, not rendered as terminal graphics. MCP form filling beyond basic questions is not implemented; cancellation remains available.
- Protocol field checks cannot prove compatibility with every future Codex version. Run the live smoke test when backend behavior changes.
