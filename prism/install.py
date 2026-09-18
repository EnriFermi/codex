#!/usr/bin/env python3
"""Install a built native fork with the matching official helper package (Unix)."""

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_symlink(target, path):
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.symlink_to(target)
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--binary", type=Path, default=ROOT / "codex-rs/target/release/codex"
    )
    parser.add_argument(
        "--stock-package",
        type=Path,
        default=Path.home() / ".codex/packages/standalone/current",
    )
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    args = parser.parse_args()
    pin = json.loads((ROOT / "prism/upstream.json").read_text())
    package = args.stock_package.resolve(strict=True)
    manifest = json.loads((package / "codex-package.json").read_text())
    version = pin["tag"].removeprefix("rust-v")
    if manifest["version"] != version:
        parser.error(
            f"Need official helper package {version}, got {manifest['version']}"
        )
    required = ["bin/codex-code-mode-host", "codex-path/rg"]
    if "linux" in manifest.get("target", ""):
        required.extend(["codex-resources/bwrap", "codex-resources/zsh/bin/zsh"])
    for relative in required:
        if not (package / relative).is_file():
            parser.error(f"Missing official package helper: {relative}")
    binary = args.binary.resolve(strict=True)
    binary_hash = digest(binary)
    prefix = args.prefix.expanduser().resolve()
    data = prefix / "share/codex-prism"
    releases = data / "releases"
    releases.mkdir(parents=True, exist_ok=True)
    release = releases / f"{version}-{binary_hash[:16]}"
    if not release.exists():
        stage = Path(tempfile.mkdtemp(prefix=".install-", dir=releases))
        try:
            shutil.copytree(package, stage, symlinks=True, dirs_exist_ok=True)
            entrypoint = stage / "bin/codex"
            entrypoint.unlink()
            shutil.copy2(binary, entrypoint)
            commit = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
            provenance = {
                "upstream": pin,
                "source_commit": commit,
                "source_dirty": bool(
                    subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)
                ),
                "binary_sha256": binary_hash,
                "official_helpers_from": str(package),
                "official_helpers_target": manifest.get("target"),
                "helper_sha256": {name: digest(package / name) for name in required},
            }
            # Target describes our CLI; helper provenance records their original target.
            rust_info = subprocess.check_output(
                ["rustc", "-vV"], cwd=ROOT / "codex-rs", text=True
            )
            manifest["target"] = next(
                line.removeprefix("host: ")
                for line in rust_info.splitlines()
                if line.startswith("host: ")
            )
            (stage / "codex-package.json").write_text(
                json.dumps(manifest, indent=2) + "\n"
            )
            (stage / "prism-build.json").write_text(
                json.dumps(provenance, indent=2) + "\n"
            )
            reported = subprocess.check_output(
                [str(entrypoint), "--version"], text=True
            ).strip()
            if version not in reported:
                raise RuntimeError(
                    f"Packaged executable has unexpected version: {reported}"
                )
            stage.rename(release)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    if digest(release / "bin/codex") != binary_hash:
        raise RuntimeError("Existing release does not match the built executable")
    for relative in required:
        if digest(release / relative) != digest(package / relative):
            raise RuntimeError(f"Helper mismatch: {relative}")

    config_root = (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "codex-prism"
    )
    config_root.mkdir(parents=True, exist_ok=True)
    config = config_root / "native.toml"
    if not config.exists():
        shutil.copy2(ROOT / "prism/native.example.toml", config)
    bindir = prefix / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    launcher = bindir / "codex-prism"
    legacy = bindir / "codex-prism-legacy"
    if launcher.is_symlink() and not os.path.lexists(legacy):
        legacy.symlink_to(launcher.resolve())
    elif (
        launcher.exists()
        and not launcher.is_symlink()
        and "# Codex Prism native launcher" not in launcher.read_text()
    ):
        raise RuntimeError(f"Refusing to overwrite an unknown launcher: {launcher}")
    current = data / "current"
    if current.is_symlink() and current.resolve() != release:
        atomic_symlink(current.resolve(), data / "previous")
    atomic_symlink(release, current)
    script = f"""#!/bin/sh
# Codex Prism native launcher
export CODEX_PRISM="${{CODEX_PRISM:-1}}"
if [ -z "${{CODEX_PRISM_CONFIG:-}}" ]; then
    CODEX_PRISM_CONFIG={shlex.quote(str(config))}
fi
export CODEX_PRISM_CONFIG
if [ "$CODEX_PRISM" = 1 ]; then
    exec {shlex.quote(str(current / "bin/codex"))} -c show_raw_agent_reasoning=true "$@"
fi
exec {shlex.quote(str(current / "bin/codex"))} "$@"
"""
    temporary = launcher.with_name(f".codex-prism-{os.getpid()}")
    temporary.write_text(script)
    temporary.chmod(0o755)
    temporary.replace(launcher)
    print(f"Installed: {launcher}\nPackage: {release}\nAppearance: {config}")
    print("Native codex, authentication and config.toml were not modified.")


if __name__ == "__main__":
    main()
