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
| `widgets.py` | Paged blocks, output folding, request dialogs |
| `app.py` | Thread/turn lifecycle, steering, resume, navigation, search, keybindings |
| `config.py` / `app.tcss` | Appearance contract and theme defaults |
| `cli.py` | Entry point, doctor, demo/replay/export modes |

Both reasoning streams are handled as supplied by app-server. Raw content is not inferred from a summary. Missing content remains missing. No extra prompt asks a model to disclose private reasoning. Codex's existing `show_raw_agent_reasoning` setting is left in place.

Command output deltas are accumulated. A shorter final `aggregatedOutput` does not replace a longer stream. The complete final item is also available in the event inspector. The journal preserves the received sequence, including unknown notifications. Tool metadata that has no dedicated renderer stays available through its item JSON or the recording.

Large blocks use rendering pages. Search, copy, and export operate on the complete in-memory entry, not the preview/page. Recordings use compression, not summarization. Long histories currently keep entries and their card widgets in memory; viewport virtualization and disk-backed indexing are future work.

`AppServer` owns only its child process. It does not connect to or restart another running Codex/dispatcher server. On normal exit Prism requests turn interruption and closes this child. Process death fails outstanding RPC requests. Unknown server requests receive a JSON-RPC error instead of waiting forever. Structured command/file/permission approvals are explicit, one-use replies; a cancelled permission request grants no permissions.

## Compatibility evidence

The checked-in `compatibility.json` was generated from **installed Codex 0.153.3**. The required protocol fields and schema fingerprints come from `codex app-server generate-json-schema`, not guesses from a differently versioned web page.

The upstream app-server routes `ReasoningRawContentDelta` and command-output deltas to v2 notifications in `codex-rs/app-server/src/bespoke_event_handling.rs` (source inspected during implementation). The corresponding installed schemas have separate `contentIndex` / `summaryIndex` deltas and `content` / `summary` item fields. Presence in a schema is not proof that a given provider emits raw content; the validation report distinguishes the two.

## Updating Codex

1. Update Codex using the same installation method you already use. Prism neither upgrades nor replaces the executable.
2. Run `codex-prism --doctor` to verify version and transport initialization without a model call.
3. Run `uv run python scripts/check_protocol.py`. This checks the presence of fields Prism consumes; it is a structural guard, not a proof of behavioral compatibility.
4. Run `uv run pytest -q` and, when needed, the opt-in `scripts/smoke_live.py` integration check.
5. Record a reviewed new schema manifest using `uv run python scripts/check_protocol.py --write` and commit it alongside necessary adapter changes.

For rollback, point `--codex /absolute/path/to/older/codex` at a retained binary. Prism and engine releases can be versioned independently. There is no upstream engine fork to merge.

## Updating Prism

Use a branch, implement a change, run lint/format/tests, then `uv build`. Dependencies are pinned by `uv.lock`; ordinary installs use `uv sync --locked`. Upgrade dependencies intentionally and rerun the UI tests. The GitHub Actions workflow performs the offline suite on Python 3.11 and 3.12 without Codex credentials or model calls.

Do not commit recordings from real sessions. `private/` and `*.trace.jsonl[.gz]` are ignored. Checked-in screenshots and demo data are synthetic. The optional live smoke test uses a single harmless command and records into `private/`; its model call uses the locally configured account.
