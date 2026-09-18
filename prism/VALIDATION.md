# Native fork validation — 2026-09-18

Baseline: `openai/codex` tag `rust-v0.153.3`, commit
`b1a547b1f73ce86205d9222ac19cff334b3b7a2e`. This is the version installed on the
host before the migration. The newer `0.155.0` release is recorded as an update
candidate, not a tested baseline.

## Verified locally

- Native TUI suite: **4099 passed, 6 skipped**, using `just test` through
  `prism/test.sh`. The suite includes native approvals, permission selection,
  slash commands, session resume/fork, keyboard handling and transcript tests.
- New Prism snapshot tests cover full shell arguments, syntax colors, bounded
  output previews with complete transcript output, distinct reasoning styling
  with original text preserved, and the Bochner integral math example.
- Source parity check passes: native agent engine, CLI, protocol, permission
  handlers, slash dispatch and keymaps are identical to the pinned upstream.
- JSON schema generation from the installed official binary and the packaged
  fork produces **416 byte-identical files**, including experimental APIs.
- CLI help is identical for the root command, `exec`, `resume`, `fork`,
  `app-server`, `mcp`, `login`, `sandbox` and `features`.
- Real PTY checks passed on both the official binary and the native fork:
  startup, `/permissions`, `/model`, `/status`, `/resume`, `/theme`, `/keymap`,
  `/quit`. The session picker contained existing named sessions. Quit exited 0.
- The native `composer.submit = ["enter", "ctrl-enter"]` setting was added to
  the local user configuration after retaining a private backup. CSI-u Ctrl+Enter
  was checked with the completion popup dismissed; Enter remains the native
  slash-menu selection key. The installer itself does not edit user config.
- The packaged executable reports `codex-cli 0.153.3`; official matching
  code-mode host, ripgrep, bwrap and zsh helpers are retained and hash-checked.
- `just bazel-lock-update` completed without Bazel lock drift. The Cargo lock
  adjustment changes only local workspace package versions, not dependencies.
- Scoped `just fix -p codex-tui` and `just fmt` completed. Existing warnings in
  unchanged upstream dependency crates were left intact.

The Rust build uses Rust 1.95.0, Clang, release mode without LTO and 16 codegen
units. TUI tests use release dependencies with the TUI package at opt-level 0
to reduce test recompilation time. Local Git tests use Git 2.51.0 in a private
test-tools directory; the system Git installation is unchanged.

## Why initial test failures were fixed

The initial runner inherited `NO_COLOR=1`, `TERM_PROGRAM=vscode`, and Git 2.25.
These affect native ANSI snapshots, shortcut labels and Git fsmonitor behavior.
`prism/test.sh` provides stable terminal settings; a recent Git resolves the
native Git test failure. Upstream release snapshots still expected `0.0.0`:
the reviewed version/padding changes, plus the stable-release update command,
are enumerated with exact before/after hashes in `release-snapshots.json`.
No permission or command behavior was changed to make these tests pass.

## Scope

This establishes source/API parity and targeted local runtime coverage, not
exhaustive validation of every model, platform, terminal, MCP server or connected
service. No paid model turn was used in this validation. Hosted Actions status
and repository settings were not verified through an authenticated GitHub API.

Prism displays reasoning that the backend emits. The native backend's output
retention/truncation limits remain in force. Ctrl+T expands the received output;
it cannot reconstruct data the backend never supplied. Math rendering supports
common TeX as Unicode and preserves unsupported source; it is not full LaTeX.
