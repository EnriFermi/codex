#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../codex-rs"
# Native snapshots assume a non-interactive terminal without editor-specific
# shortcut substitutions. NO_COLOR also suppresses explicitly tested ANSI codes.
unset NO_COLOR TERM_PROGRAM TERM_PROGRAM_VERSION COLORTERM FORCE_COLOR
export TERM=dumb
export TMPDIR=/tmp
export CC="${CC:-clang}" CXX="${CXX:-clang++}"
just test -p codex-tui --locked "$@"
