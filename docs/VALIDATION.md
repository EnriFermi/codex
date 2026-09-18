# Validation

## Markdown and boxed display math — 2026-09-18

**111 offline tests pass on Python 3.12.** A recorded Bochner-integral answer reproduced two rendering bugs: unsupported `\\boxed` left the entire formula as raw LaTeX, and display math adjacent to prose was parsed inline. Common math wrappers now render, outer boxes receive a terminal frame, and both display delimiters interrupt paragraphs without requiring blank lines. The original recorded answer was re-rendered successfully; its Markdown/LaTeX source was not changed.

Regression checks cover headings, bold/italic, links, lists, tables, literal code, boxed equations, display math in lists/quotes, streaming completion, copy and export. Existing math, text-selection, command and session tests also pass. Lint, formatting and package build pass. Synthetic rendered views were inspected at 120 × 45 and 80 × 32 cells; [the new screenshot](prism-markdown.png) contains only synthetic content. No model turn was needed for this fix.

## Original Prism restored and session settings — 2026-09-18

The default launcher and GitHub `main` use the original Textual interface again. The native experiment is preserved on `archive/prism-native`, without rewriting history. The restore keeps card rendering, folding, sidebar navigation, live received reasoning, Markdown math, selection/copy, resume picker, and TOML/CSS customization.

The offline suite now covers 101 tests, including every advertised command through the composer. New checks exercise permissions at 80 × 24 and 120 × 40 cells, cancellation before Apply, full-access confirmation, atomic model/effort selection, rejection during an active turn, RPC failures, acknowledgements without applied settings, missing notifications, unrelated thread events, and paginated model lists. A stale assertion that hard-coded nine commands was updated for the expanded command registry.

On installed Codex 0.153.3, an ephemeral thread confirmed read-only, workspace, full-access and back to read-only through `thread/settings/updated`; model listing returned five models, and changing reasoning effort was confirmed. This check executed no model turn or shell tool. Protocol checks include the experimental settings APIs. Separate PTY checks covered Enter, Ctrl+Enter as LF and CSI-u, message completion against the fake server, and clean Ctrl+Q exit. SVG views of the restored cards and permissions picker were inspected, including 80 × 24 cells.

## Command dispatch and exit — 2026-09-18

**87 offline tests pass on Python 3.12.** Every advertised command (`/new`, `/resume`, `/sessions`, `/theme`, `/export`, `/stop`, `/help`, `/quit`, `/exit`) is exercised through the composer against the fake app-server. Local command dispatch is independent of the pending message request; help, theme and exit also run while disconnected or switching history. Rejected/unsupported commands retain their draft. Repeated exit requests no longer cancel the worker responsible for closing the server.

Separate Linux PTY checks of `/quit`, `/exit`, Ctrl+Q and an external SIGINT all exited with code 0, reaped the fake app-server child and left complete readable gzip journals. The Quit button is covered by UI tests. The user's Ctrl+Q failure was not reproduced in these terminals, so the host-side cause remains unverified; typed commands and the button provide alternatives. Prism still implements a subset of the stock Codex CLI's slash commands.

## Resume activation and short terminals — 2026-09-18

The previous chooser tests checked loaded rows but missed two user-visible problems: selecting `/resume` completed the draft without opening the chooser, and the 85%-height modal left only two list lines at 135 × 26 (one at 80 × 24). New regression tests failed on both behaviors before the fix.

**73 offline tests pass on Python 3.12.** They cover opening the chooser with one Enter, Ctrl+Enter, Alt+Enter, LF/Ctrl+J or click, as well as typing `/resume` fully. Tab remains completion-only. Resizing to 80 × 24, 80 × 20 and 60 × 16 keeps at least six list lines and the Resume button on screen. The compact layout allocates 14 list lines at 135 × 26.

A read-only check opened the actual chooser through `/res` + Enter against installed Codex and loaded **29 saved sessions** without an error or model call. No conversation titles or content were saved in this report. Separate Linux PTY checks exercised actual CR, LF and CSI-u Ctrl+Enter keystrokes: both synthetic session titles were visible and all three runs exited cleanly. Lint, formatting, diff checks and wheel/source builds passed.

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
