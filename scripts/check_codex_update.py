"""Check an official stable Linux x86_64 Codex package alongside the working engine.

Downloads into --work-dir, verifies GitHub's SHA-256 digest, and runs structural
and stdio initialization checks in a temporary profile. Never starts a model
turn, changes the installed engine, or replaces the reviewed protocol baseline.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from check_protocol import ROOT, check, fingerprint

ASSET = "codex-package-x86_64-unknown-linux-musl.tar.gz"
API = "https://api.github.com/repos/openai/codex/releases/"


def version_tuple(version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Expected stable X.Y.Z version, got {version!r}")
    return tuple(int(part) for part in version.split("."))


def select_release(release):
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Only published stable releases are accepted")
    tag = release["tag_name"]
    if not tag.startswith("rust-v"):
        raise ValueError(f"Unexpected upstream tag: {tag}")
    version = tag.removeprefix("rust-v")
    version_tuple(version)
    asset = next((a for a in release["assets"] if a["name"] == ASSET), None)
    if not asset:
        raise ValueError(f"Release {tag} has no complete {ASSET} package")
    expected_url = f"https://github.com/openai/codex/releases/download/{tag}/{ASSET}"
    if asset["browser_download_url"] != expected_url:
        raise ValueError("Unexpected release download URL")
    digest = asset.get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("Release asset has no valid SHA-256 digest")
    return {
        "version": version,
        "tag": tag,
        "asset": ASSET,
        "url": expected_url,
        "sha256": digest[7:],
    }


def latest_release(version=None):
    if version:
        version_tuple(version)
    url = API + (f"tags/rust-v{version}" if version else "latest")
    headers = {"User-Agent": "codex-prism-updater", "Accept": "application/vnd.github+json"}
    # CI passes only a read-scoped token to this API request, not to the engine.
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as r:
        return select_release(json.load(r))


def download_package(release, work):
    import hashlib

    archive = work / ASSET
    digest = hashlib.sha256()
    request = urllib.request.Request(release["url"], headers={"User-Agent": "codex-prism-updater"})
    size = 0
    with urllib.request.urlopen(request, timeout=60) as source, archive.open("wb") as dest:
        while block := source.read(1024 * 1024):
            size += len(block)
            if size > 512 * 1024 * 1024:
                raise ValueError("Release package exceeds the 512 MiB download limit")
            digest.update(block)
            dest.write(block)
    if digest.hexdigest() != release["sha256"]:
        raise ValueError("Release package SHA-256 mismatch")
    package = work / "package"
    package.mkdir()  # Never overlay an old extraction.
    with tarfile.open(archive) as tar:
        tar.extractall(package, filter="data")
    manifests = list(package.rglob("codex-package.json"))
    if len(manifests) != 1:
        raise ValueError("Expected one standalone package manifest")
    manifest = manifests[0]
    data = json.loads(manifest.read_text())
    if data.get("version") != release["version"] or data.get("variant") != "codex":
        raise ValueError("Standalone package identity does not match the selected release")
    entry = (manifest.parent / data["entrypoint"]).resolve()
    if not entry.is_relative_to(package.resolve()) or not entry.is_file():
        raise ValueError("Invalid standalone package entrypoint")
    return entry


def isolated_environment(profile):
    # Use an allowlist; credentials and the user's Codex profile never reach the
    # candidate process. A real HOME is still available for OS path resolution.
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["CODEX_HOME"] = str(profile)
    env["XDG_CONFIG_HOME"] = str(profile / "xdg")
    return env


def should_check(release, floor, accepted, force=False):
    current = version_tuple(release["version"])
    if current < version_tuple(floor):
        return False
    if accepted and current < version_tuple(accepted):
        return False
    return force or accepted is None or current > version_tuple(accepted)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def run(args):
    args.work_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale report outputs before any possible failure or skip.
    report_path = args.work_dir / "candidate.json"
    report_path.unlink(missing_ok=True)
    (args.work_dir / "protocol.json").unlink(missing_ok=True)
    result_path = args.work_dir / "result.json"
    result = {"status": "failed", "model_validation": "not_run"}
    write_json(result_path, result)
    release = latest_release(args.version)
    baseline = json.loads(args.baseline.read_text())
    floor = baseline["codex"].removeprefix("codex-cli ")
    accepted = json.loads(args.accepted.read_text())["version"] if args.accepted.exists() else None
    if not should_check(release, floor, accepted, args.force):
        result.update(
            status="skipped",
            version=release["version"],
            reason="Already checked or older than baseline",
        )
        write_json(result_path, result)
        return result
    print(
        f"Checking official Codex {release['version']} alongside the installed engine", flush=True
    )
    # Fresh extraction per attempt; a failed run cannot contaminate a retry.
    with tempfile.TemporaryDirectory(prefix="candidate-", dir=args.work_dir) as temp:
        candidate_dir = Path(temp).resolve()
        binary = download_package(release, candidate_dir)
        profile = candidate_dir / "profile"
        profile.mkdir()
        env = isolated_environment(profile)
        protocol, _ = check(str(binary), args.baseline, env=env)
        write_json(args.work_dir / "protocol.json", protocol)
        if protocol["codex"] != f"codex-cli {release['version']}":
            raise ValueError("Executable version does not match release metadata")
        if protocol["changes"]:
            result.update(
                status="review_required", version=release["version"], changes=protocol["changes"]
            )
            write_json(result_path, result)
            raise ValueError("Protocol drift requires review; see protocol.json")
        doctor = subprocess.run(
            [
                sys.executable,
                "-c",
                "from codex_prism.cli import main; main()",
                "--doctor",
                "--codex",
                str(binary),
            ],
            env=env,
            cwd=candidate_dir,
            text=True,
            capture_output=True,
            check=True,
            timeout=90,
        )
        handshake = json.loads(doctor.stdout)
        if handshake.get("handshake") != "ok" or handshake.get("codex") != protocol["codex"]:
            raise ValueError("Unexpected handshake report")
    report = {
        "version": release["version"],
        "release": f"https://github.com/openai/codex/releases/tag/{release['tag']}",
        "platform": "x86_64-unknown-linux-musl",
        "asset": release["asset"],
        "asset_sha256": release["sha256"],
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "prism_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "prism_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
        "status": "structural_and_handshake_checks_passed",
        "protocol": protocol,
        "handshake": "ok",
        "model_validation": "not_run",
        "working_engine_changed": False,
    }
    write_json(report_path, report)
    result.update(status="passed", version=release["version"], report_sha256=fingerprint(report))
    write_json(result_path, result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", help="Stable release X.Y.Z (default: upstream latest)")
    p.add_argument("--work-dir", type=Path, default=ROOT / "private/codex-update")
    p.add_argument("--baseline", type=Path, default=ROOT / "docs/protocol-baseline.json")
    p.add_argument("--accepted", type=Path, default=ROOT / "docs/codex-candidate.json")
    p.add_argument(
        "--force", action="store_true", help="Recheck the accepted version; never downgrade"
    )
    p.add_argument("--github-output", type=Path, help="Actions step output file")
    args = p.parse_args()
    result = run(args)
    print(json.dumps(result, indent=2))
    if args.github_output:
        with args.github_output.open("a") as f:
            f.write(f"update={'true' if result['status'] == 'passed' else 'false'}\n")
            f.write(f"version={result['version']}\n")


if __name__ == "__main__":
    main()
