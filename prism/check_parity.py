#!/usr/bin/env python3
"""Fail if the fork modifies files outside its reviewed presentation surface."""

import hashlib
import json
import subprocess
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[1]
PIN = json.loads((ROOT / "prism/upstream.json").read_text())
ALLOWED = {
    "README.md",
    "codex-rs/Cargo.lock",
    ".github/workflows/blocking-ci.yml",
    ".github/workflows/postmerge-ci.yml",
    ".github/workflows/prism-native.yml",
    ".github/workflows/prism-upstream.yml",
    "codex-rs/tui/src/lib.rs",
    "codex-rs/tui/src/markdown_render.rs",
    "codex-rs/tui/src/history_cell/messages.rs",
    "codex-rs/tui/src/history_cell/messages_tests.rs",
    "codex-rs/tui/src/exec_cell/mod.rs",
    "codex-rs/tui/src/exec_cell/render.rs",
    "codex-rs/tui/src/exec_cell/prism.rs",
    "codex-rs/tui/src/exec_cell/prism_tests.rs",
    "codex-rs/tui/src/prism.rs",
    "codex-rs/tui/src/prism_tests.rs",
    "codex-rs/tui/src/prism_math.rs",
    "codex-rs/tui/src/prism_math_tests.rs",
}


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main():
    base = PIN["commit"]
    snapshot_adjustments = json.loads(
        (ROOT / "prism/release-snapshots.json").read_text()
    )
    for path, evidence in snapshot_adjustments.items():
        assert path.startswith("codex-rs/tui/src/") and (
            path.endswith(".snap")
            or path == "codex-rs/tui/src/chatwidget/rendering_tests.rs"
        )
        original = subprocess.check_output(["git", "show", f"{base}:{path}"], cwd=ROOT)
        assert hashlib.sha256(original).hexdigest() == evidence["upstream_sha256"], path
        assert (
            hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            == evidence["fork_sha256"]
        ), path
    # Publishing upstream tags to the fork would trigger release workflows.
    # The immutable commit is required; verify the tag too when fetched locally.
    tag = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{PIN['tag']}^{{commit}}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if tag.returncode == 0:
        assert tag.stdout.strip() == base, "Tag/pin mismatch"
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", base, "HEAD"], cwd=ROOT, check=True
    )
    changed = set(git("diff", "--name-only", base).splitlines())
    changed.update(git("ls-files", "--others", "--exclude-standard").splitlines())
    unexpected = sorted(
        path
        for path in changed
        if path not in ALLOWED
        and path not in snapshot_adjustments
        and not path.startswith("prism/")
        and not (
            path.startswith("codex-rs/tui/src/")
            and "/snapshots/" in path
            and "prism" in Path(path).name
            and path.endswith(".snap")
        )
    )
    assert not unexpected, "Changes outside presentation surface:\n" + "\n".join(
        unexpected
    )

    # Release tags can carry workspace version 0.0.0 in Cargo.lock. Allow ONLY
    # normalization of local package versions; preserve all external packages.
    before = tomllib.loads(git("show", f"{base}:codex-rs/Cargo.lock"))
    after = tomllib.loads((ROOT / "codex-rs/Cargo.lock").read_text())
    for lock in (before, after):
        for package in lock["package"]:
            if "source" not in package:
                package["version"] = "workspace"
    assert before == after, "Dependencies changed: review and update the parity policy"
    print(
        f"PASS: native engine, CLI, protocol, command dispatch, permissions and keymaps match {PIN['tag']}."
    )
    print(f"Reviewed presentation/packaging surface: {len(changed)} changed files.")
    print(
        "This checks source parity; runtime behavior is checked separately by TUI tests and PTY smoke tests."
    )


if __name__ == "__main__":
    main()
