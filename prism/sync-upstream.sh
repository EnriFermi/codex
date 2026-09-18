#!/usr/bin/env bash
# Prepare an isolated update branch. Conflicts and validation require review.
set -euo pipefail
cd "$(dirname "$0")/.."
tag="${1:?Usage: prism/sync-upstream.sh rust-vX.Y.Z}"
[[ "$tag" =~ ^rust-v[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Expected a stable release tag.' >&2; exit 2; }
[[ -z "$(git status --porcelain)" ]] || { echo 'Commit or stash local work first.' >&2; exit 2; }
git fetch upstream "refs/tags/$tag:refs/tags/$tag"
git switch -c "update/$tag"
git merge --no-edit "$tag"
python3 - "$tag" <<'PY'
import json
from pathlib import Path
import subprocess
import sys

path = Path("prism/upstream.json")
pin = json.loads(path.read_text())
pin["tag"] = sys.argv[1]
pin["commit"] = subprocess.check_output(["git", "rev-parse", f'{sys.argv[1]}^{{commit}}'], text=True).strip()
path.write_text(json.dumps(pin, indent=2) + "\n")
PY
cat <<'TEXT'
Upstream merged on an update branch; nothing installed or pushed.
Follow prism/README.md: inspect the diff, check parity, run TUI tests and Clippy,
build, then validate native commands in a terminal. Commit the updated pin.
If a merge stopped on conflicts, resolve them and update prism/upstream.json
to the new tag and its peeled commit before validation.
TEXT
