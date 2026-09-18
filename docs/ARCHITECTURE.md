# Architecture and update contract

Prism is an independent terminal frontend to the locally installed Codex engine. This avoids carrying rendering patches through upstream Rust refactors. The backend retains its existing authentication, provider configuration, tools, and permission enforcement. The client never invokes a model endpoint directly.

```text
Textual terminal UI
    │ user prompts / explicit approval replies
    ▼
AppServer (dedicated subprocess, stdio JSON-RPC)
    │ notifications / server requests
    ├── private append-only JSONL/gzip recording
    └── Trace reducer → typed entries → highlighted cards
```

## Source map

| Module | Responsibility |
| --- | --- |
| `transport.py` | Handshake, request correlation, timeouts, server requests, EOF/process cleanup |
| `model.py` | Item/delta reduction, content/summary separation, full commands and received output |
| `storage.py` | Private append-only recordings, offline replay, Markdown export |
| `rendering.py` | Safe display of terminal text; Pygments shell/log lexers and themes |
| `math_rendering.py` | Math delimiters parsed before Markdown escapes; Unicode math, literal fallback for unknown/incomplete TeX |
| `selectable.py` | Rich renderables materialized as styled text for Textual mouse selection |
| `sessions.py` | Progressive session listing, preview/title/path search and conversation selection |
| `session_settings.py` | Permission/model pickers, model pagination, confirmed thread settings |
| `widgets.py` | Paged blocks, output folding, request dialogs |
| `app.py` | Thread/turn lifecycle, steering, resume, navigation, search, keybindings |
| `config.py` / `app.tcss` | Appearance contract and theme defaults |
| `cli.py` | Entry point, doctor, demo/replay/export modes |

Both reasoning streams are handled as supplied by app-server. Raw content is not inferred from a summary. Missing content remains missing. No extra prompt asks a model to disclose private reasoning. Codex's existing `show_raw_agent_reasoning` setting is left in place.

Command output deltas are accumulated. A shorter final `aggregatedOutput` does not replace a longer stream. The complete final item is also available in the event inspector. The journal preserves the received sequence, including unknown notifications. Tool metadata that has no dedicated renderer stays available through its item JSON or the recording.

Large blocks use rendering pages. Search, copy, and export operate on the complete in-memory entry, not the preview/page. Recordings use compression, not summarization. Long histories currently keep entries and their card widgets in memory; viewport virtualization and disk-backed indexing are future work.

Textual 8 supplies mouse selection. Rich Markdown/Syntax blocks expose their rendered characters through `SelectableText`, so selection includes the text the user sees. Ctrl+C copies the selection; card Copy preserves the full source. While a trace selection exists, UI reduction waits in the event queue; incoming events are still journaled. Esc/click clears the selection and releases queued updates.

Math conversion is display-only. Markdown-It recognizes dollar/bracket math and fenced `math`; regular code is kept literal. `pylatexenc` parses TeX without executing a compiler, and the renderer preserves norm bars, grouping of nested fractions and unsupported scripts. Unknown macros or incomplete expressions fall back to literal TeX. Unicode is a portable text approximation, not complete LaTeX typography.

The session chooser consumes `thread/list` pages with an empty provider filter (all providers) and the default interactive source filter. Search is local across loaded title/preview/path metadata; older pages continue arriving in the background. Selecting a row uses the existing `thread/resume` and paginated history path. A failed history load leaves the current trace intact.

`AppServer` owns only its child process. It does not connect to or restart another running Codex/dispatcher server. On normal exit Prism requests turn interruption and closes this child. Process death fails outstanding RPC requests. Unknown server requests receive a JSON-RPC error instead of waiting forever. Structured command/file/permission approvals are explicit, one-use replies; a cancelled permission request grants no permissions.

## Compatibility evidence

The checked-in `compatibility.json` was generated from **installed Codex 0.153.3**. The required protocol fields and schema fingerprints come from `codex app-server generate-json-schema`, not guesses from a differently versioned web page.

The upstream app-server routes `ReasoningRawContentDelta` and command-output deltas to v2 notifications in `codex-rs/app-server/src/bespoke_event_handling.rs` (source inspected during implementation). The corresponding installed schemas have separate `contentIndex` / `summaryIndex` deltas and `content` / `summary` item fields. Presence in a schema is not proof that a given provider emits raw content; the validation report distinguishes the two.

## Updating Codex

Follow [UPDATING.md](UPDATING.md). The scheduled workflow downloads a complete stable package alongside the working installation, verifies its digest, runs the offline suite/build, compares consumed field shapes against `protocol-baseline.json`, and initializes a dedicated app-server with a temporary profile. It opens a report-only PR after success; it never installs a default engine or changes the reviewed baseline.

`compatibility.json` is the original field-presence report for 0.153.3. `protocol-baseline.json` records the reviewed structural contract from that same engine. A future `codex-candidate.json` records automated checks on a newer release, explicitly without model validation. None of these is a promise that every provider emits every event.

The structural guard resolves references and compares types, enums, constraints, and nested shapes for the declared consumed fields. It checks method availability and new required request/reply fields. Unknown top-level optional fields are ignored; changed nested shapes conservatively require review even if backward compatible. Coverage is declared in `scripts/check_protocol.py`, not the entire upstream protocol.

For rollback, point `--codex /absolute/path/to/older/package/bin/codex` at a retained complete package, including resources and companion executables. Prism and engine releases can be versioned independently. There is no upstream engine fork to merge.

## Updating Prism

The live client opts into `experimentalApi` for `thread/settings/update` and `thread/settings/updated`. The update response acknowledges queueing; `SessionSettings` waits for the applied-settings notification before reporting success. If no notification arrives, a resume of the already loaded thread without overrides reads its actual settings; mismatches are reported as failures. Settings changes require an idle conversation and explicit Apply. Cancelling the model or effort picker changes neither. Model catalogs are paginated, and inherited/custom permission settings are retained unless the user selects a preset.

The protocol guard generates schemas with `--experimental` and covers these methods, notification fields, permission profiles, model catalogs, and reasoning effort. The reviewed baseline still uses Codex 0.153.3. Upstream changes to this experimental contract require review before installation.

Use a branch, implement a change, run lint/format/tests, then `uv build`. Dependencies are pinned by `uv.lock`; ordinary installs use `uv sync --locked`. Upgrade dependencies intentionally and rerun the UI tests. The GitHub Actions workflow performs the offline suite on Python 3.11 and 3.12 without Codex credentials or model calls.

Do not commit recordings from real sessions. `private/` and `*.trace.jsonl[.gz]` are ignored. Checked-in screenshots and demo data are synthetic. The optional live smoke test uses a single harmless command and records into `private/`; its model call uses the locally configured account.
