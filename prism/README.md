# Codex Prism: native interface

Prism now builds the real Codex TUI. The earlier Python/Textual client implemented
only a subset of native operations; keeping it as the default caused missing
commands and inconsistent behavior. It is preserved on `legacy/prism-python`.

The baseline is recorded in [`upstream.json`](upstream.json). Prism modifies only
the reviewed display surface, packaging and fork maintenance. The native CLI,
agent engine, slash-command dispatch, permissions dialogs, session browser,
authentication, tools, MCP, skills, approvals and keymaps remain upstream code.
Source identity is enforced by `python3 prism/check_parity.py`.

## Run and configure

```sh
codex-prism                 # native Codex with Prism presentation
codex-prism resume          # native session picker
codex-prism resume --all    # sessions from all working directories
CODEX_PRISM=0 codex-prism   # original presentation, same native binary
codex-prism-legacy         # previous Python client, if already installed
```

Use `/permissions`, `/model`, `/resume`, `/status`, `/theme`, `/keymap`, `/copy`,
`/quit` and other native commands normally. Slash suggestions and their help text
are native. Enter sends messages; available bindings and terminal-specific key
support are shown by `/keymap`. This fork does not replace keyboard dispatch.

To send with Ctrl+Enter as well, use `/keymap` or add this native setting to
`~/.codex/config.toml` (it applies to both native Codex launchers):

```toml
[tui.keymap.composer]
submit = ["enter", "ctrl-enter"]
```

The terminal must transmit Ctrl+Enter distinctly; otherwise it is indistinguishable
from Enter at the application boundary. The local installation was checked with
the CSI-u Ctrl+Enter sequence in the composer. Native slash-completion menus
still use Enter to choose a command; Escape closes that menu and returns to the
composer. This behavior remains the same as the pinned upstream version.

Prism prints complete received command arguments with shell highlighting, gives
reasoning a separate label/color, and previews both ends of command output.
**Ctrl+T** opens the native transcript with expanded command output. Use `/theme`
to choose syntax colors, including custom TextMate themes in
`$CODEX_HOME/themes/` (normally `~/.codex/themes/`).

Copy the last assistant response with native `/copy`. For mouse selection use
the terminal's selection gesture; in terminals that capture the mouse this is
usually Shift+drag. `--no-alt-screen` retains normal terminal scrollback. No
Textual widget intercepts selection anymore.

Appearance is configured in `~/.config/codex-prism/native.toml`, or under
`$XDG_CONFIG_HOME`, using [`native.example.toml`](native.example.toml).
Set `CODEX_PRISM_CONFIG` for another file. Restart to apply edits. A bad setting
produces a startup warning and uses defaults rather than blocking launch.

The launcher supplies native `show_raw_agent_reasoning=true` as a command-line
default. Override with `codex-prism -c show_raw_agent_reasoning=false` if needed.
It displays reasoning events the backend provides; it cannot recover reasoning
the service did not emit. It does not modify `~/.codex/config.toml`, credentials
or session storage. All native CLI arguments and subcommands pass through.

Math in `$...$`, `$$...$$`, `\(...\)` and `\[...\]` is rendered as readable
Unicode when supported. For example, `\int_0^1 t^2\,dt=\frac13` becomes
`∫₀¹ t² dt=⅓`. Code blocks and links are excluded; unknown TeX stays in source
form. This is a terminal renderer, not a complete LaTeX typesetter. Original
message and session data are preserved.

## Build and install on Linux

Requirements: the Rust toolchain pinned in `codex-rs/rust-toolchain.toml`, Clang,
libclang, OpenSSL development headers, pkg-config, Python 3.11+, and the official
standalone Codex package **of the pinned version**. The installer copies its
matching code-mode host, ripgrep, bwrap and bundled zsh into an isolated package.

```sh
git clone git@github.com:EnriFermi/codex.git codex-native
cd codex-native
git remote add upstream git@github.com:openai/codex.git
python3 prism/check_parity.py
./prism/build.sh
python3 prism/install.py
```

Use `--stock-package /path/to/package` when the official package is not at
`~/.codex/packages/standalone/current`. The install is versioned under
`~/.local/share/codex-prism/releases/`; `current` selects the active package and
`previous` retains the prior native install. Each package includes hashes and
source provenance in `prism-build.json`. The ordinary `codex` executable is not
replaced. A pre-existing Python launcher is preserved as `codex-prism-legacy`.

Builds disable release LTO to keep local iteration practical. The checked-in
Cargo lockfile normalizes local workspace versions from the upstream release
tag; external dependency versions are unchanged. The initial supported and
validated installation target is Linux x86_64. Other upstream platforms remain
in source but have not been validated for this fork.

The release tag still carries snapshot fixtures for version `0.0.0`. Reviewed
version/padding adjustments are recorded with before/after hashes in
`release-snapshots.json`; the parity check rejects further edits to these files.
`prism/test.sh` provides a stable terminal environment for the native suite.
Use a recent Git: the host's Git 2.25 does not support the boolean fsmonitor
configuration used by native tests; local validation uses Git 2.51.

## Update from upstream

`Check native Codex updates` runs daily and can be started manually in Actions.
When a newer stable release appears, it proposes a candidate-report PR; this
does not silently change the code or installed binary. GitHub must allow Actions
to create pull requests (Settings → Actions → General → Workflow permissions).
The actual update is a reviewed native merge using the steps below.

Keep `origin` pointing to this fork and `upstream` to `openai/codex`. Native
upstream ancestry is preserved, so updates use a normal merge, not a rewritten
copy of upstream source. Start from a clean working tree:

```sh
./prism/sync-upstream.sh rust-vX.Y.Z
```

This fetches the stable tag, creates `update/rust-vX.Y.Z`, merges it, and updates
the pin. It does not install or push. If conflicts occur, resolve them without
discarding upstream command handlers, finish the merge, and update the pin's
tag and peeled commit (`git rev-parse 'rust-vX.Y.Z^{commit}'`). Then review and run:

```sh
python3 prism/check_parity.py
./prism/test.sh
cd codex-rs
CC=clang CXX=clang++ just fix -p codex-tui
just fmt
cd ..
./prism/build.sh
```

Install the matching official helper package in a separate location if needed,
then install the fork with `--stock-package`. Check `/permissions`, `/model`,
`/resume`, `/status`, `/quit`, command output and a real turn before merging the
update branch. If the release tag needs local Cargo.lock normalization, inspect
that diff and run `just bazel-lock-update`; the parity check rejects external
dependency changes beyond the newly pinned upstream version.

Also recheck the version-specific snapshot adjustments against the new tag;
their pinned upstream hashes deliberately fail if upstream changes a fixture.

Commit the pin and reviewed adjustments, then merge the update branch into
`main` and push over SSH. CI runs source parity and the native TUI suite. The
upstream internal CI entrypoints are gated to `openai/codex`; they rely on
upstream runners and infrastructure. This fork has its own workflow instead.
Passing source parity does not prove every runtime scenario, so keep the TUI
suite and terminal checks as update gates.
