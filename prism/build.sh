#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../codex-rs"
export PATH="$HOME/.cargo/bin:$PATH"
# Clang avoids the aws-lc compiler self-test failure with older GCC versions.
export CC="${CC:-clang}" CXX="${CXX:-clang++}"
export CARGO_PROFILE_RELEASE_LTO=false
export CARGO_PROFILE_RELEASE_CODEGEN_UNITS=16
export CARGO_PROFILE_RELEASE_DEBUG=0
export CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-8}"
cargo build --release --locked -p codex-cli --bin codex
