# Validation — 2026-09-16

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

The final count and status are recorded in [validation-results.json](validation-results.json). Lint, formatting, build and installed CLI checks are run separately. The CI workflow is prepared for Python 3.11 and 3.12; remote CI has not been run because the repository has not been published.

## Visual checks

The terminal UI was rendered at 132 × 48 cells, with command, folded output and expanded-output views. Screenshots were inspected after enabling color in the test process (the agent execution environment sets `NO_COLOR`). PNG previews use JetBrains Mono for rendering; the app itself uses your terminal's font.

## Limits

- No claim of unavailable server-side reasoning or reconstruction of bytes the server never sends.
- macOS/Windows terminal behavior and OSC 52 clipboard integration were not exercised on physical terminals; Linux headless TUI and a PTY launch are covered locally.
- Histories currently retain card widgets in memory. Very large histories are not viewport-virtualized.
- Image events are represented as metadata, not rendered as terminal graphics. MCP form filling beyond basic questions is not implemented; cancellation remains available.
- Protocol field checks cannot prove compatibility with every future Codex version. Run the live smoke test when backend behavior changes.
