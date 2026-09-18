#!/usr/bin/env python3
"""Record an available stable upstream release without changing the pinned code."""

import json
import os
import re
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
pin = json.loads((root / "prism/upstream.json").read_text())
headers = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "codex-prism-upstream-check",
}
if token := os.environ.get("GH_TOKEN"):
    headers["Authorization"] = f"Bearer {token}"
request = urllib.request.Request(
    "https://api.github.com/repos/openai/codex/releases/latest", headers=headers
)
with urllib.request.urlopen(request, timeout=30) as response:
    release = json.load(response)
tag = release["tag_name"]
if (
    release["draft"]
    or release["prerelease"]
    or not re.fullmatch(r"rust-v\d+\.\d+\.\d+", tag)
):
    raise SystemExit("Upstream latest is not a stable Codex release; inspect manually.")
version = lambda value: tuple(map(int, value.removeprefix("rust-v").split(".")))
available = version(tag) > version(pin["tag"])
if available:
    candidate = {
        "tag": tag,
        "url": release["html_url"],
        "published_at": release["published_at"],
        "current_tag": pin["tag"],
        "validation": "Not merged or tested. Prepare and validate an update branch before installing.",
    }
    (root / "prism/upstream-candidate.json").write_text(
        json.dumps(candidate, indent=2) + "\n"
    )
if output := os.environ.get("GITHUB_OUTPUT"):
    with open(output, "a") as stream:
        stream.write(f"update={str(available).lower()}\nversion={tag}\n")
print(f"Pinned: {pin['tag']}; latest stable: {tag}; update available: {available}")
