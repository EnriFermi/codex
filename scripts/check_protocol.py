"""Validate the installed Codex schema without connecting to a model.

Run after updating Codex. --write records a reviewable compatibility manifest.
Unknown added fields are compatible. Missing required methods/fields are not.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

CONTRACT = {
    "InitializeParams": {"clientInfo"},
    "ThreadStartParams": {"cwd", "model", "sandbox", "approvalPolicy"},
    "ThreadResumeParams": {"threadId"},
    "TurnStartParams": {"threadId", "input"},
    "TurnSteerParams": {"threadId", "input", "expectedTurnId"},
    "TurnInterruptParams": {"threadId", "turnId"},
    "ReasoningTextDeltaNotification": {"itemId", "delta", "contentIndex"},
    "ReasoningSummaryTextDeltaNotification": {"itemId", "delta", "summaryIndex"},
    "CommandExecutionOutputDeltaNotification": {"itemId", "delta"},
    "CommandExecutionRequestApprovalResponse": {"decision"},
    "FileChangeRequestApprovalResponse": {"decision"},
    "ToolRequestUserInputResponse": {"answers"},
}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--codex", default="codex")
    p.add_argument("--write", action="store_true")
    args = p.parse_args()
    version = subprocess.check_output([args.codex, "--version"], text=True).strip()
    details = {}
    with tempfile.TemporaryDirectory(prefix="prism-schema-") as temp:
        subprocess.run(
            [args.codex, "app-server", "generate-json-schema", "--out", temp], check=True
        )
        root = Path(temp)
        for name, fields in CONTRACT.items():
            paths = list(root.rglob(name + ".json"))
            if not paths:
                raise SystemExit(f"INCOMPATIBLE: missing {name}")
            data = json.loads(paths[0].read_text())
            if missing := fields - data.get("properties", {}).keys():
                raise SystemExit(f"INCOMPATIBLE: {name} is missing {sorted(missing)}")
            details[name] = {
                "fields_checked": sorted(fields),
                "schema_sha256": hashlib.sha256(paths[0].read_bytes()).hexdigest(),
            }
        item = json.loads((root / "v2/ItemStartedNotification.json").read_text())
        variants = item["definitions"]["ThreadItem"]["oneOf"]
        for kind, fields in {
            "reasoning": {"content", "summary"},
            "commandExecution": {"command", "aggregatedOutput", "exitCode"},
        }.items():
            variant = next(v for v in variants if v["properties"]["type"]["enum"] == [kind])
            if missing := fields - variant["properties"].keys():
                raise SystemExit(f"INCOMPATIBLE: {kind} is missing {sorted(missing)}")
    report = {
        "codex": version,
        "result": "compatible",
        "transport": "stdio JSON-RPC",
        "contract": details,
    }
    if args.write:
        target = Path(__file__).resolve().parents[1] / "docs/compatibility.json"
        target.write_text(json.dumps(report, indent=2) + "\n")
        print(target)
    print(f"{version}: required protocol fields are compatible")


if __name__ == "__main__":
    main()
