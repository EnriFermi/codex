"""Check consumed app-server fields against a reviewed structural baseline.

No model call. Unknown top-level fields are ignored. Changes to consumed field
shapes or new required request fields stop automation for human review. This is
intentionally conservative, not a complete JSON Schema compatibility proof.
"""

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = {
    "InitializeParams": {"clientInfo", "capabilities"},
    "InitializeResponse": {"userAgent"},
    "ThreadStartParams": {"cwd", "model", "sandbox", "approvalPolicy"},
    "ThreadResumeParams": {"threadId", "excludeTurns"},
    "ThreadStartResponse": {
        "model",
        "sandbox",
        "approvalPolicy",
        "approvalsReviewer",
        "activePermissionProfile",
        "reasoningEffort",
    },
    "ThreadResumeResponse": {
        "model",
        "sandbox",
        "approvalPolicy",
        "approvalsReviewer",
        "activePermissionProfile",
        "reasoningEffort",
    },
    "ThreadSettingsUpdateParams": {
        "threadId",
        "permissions",
        "approvalPolicy",
        "approvalsReviewer",
        "model",
        "effort",
    },
    "ThreadSettingsUpdatedNotification": {"threadId"},
    "ModelListParams": {"cursor", "limit"},
    "ModelListResponse": {"nextCursor"},
    "ThreadListParams": {"limit", "sortKey", "cursor", "modelProviders"},
    "ThreadTurnsListParams": {"threadId", "itemsView", "sortDirection", "limit", "cursor"},
    "TurnStartParams": {"threadId", "input"},
    "TurnSteerParams": {"threadId", "input", "expectedTurnId"},
    "TurnInterruptParams": {"threadId", "turnId"},
    "ReasoningTextDeltaNotification": {"itemId", "delta", "contentIndex"},
    "ReasoningSummaryTextDeltaNotification": {"itemId", "delta", "summaryIndex"},
    "CommandExecutionOutputDeltaNotification": {"itemId", "delta"},
    "CommandExecutionRequestApprovalResponse": {"decision"},
    "FileChangeRequestApprovalResponse": {"decision"},
    "PermissionsRequestApprovalResponse": {"permissions", "scope"},
    "ToolRequestUserInputResponse": {"answers"},
    "McpServerElicitationRequestResponse": {"action"},
}
METHODS = {
    "ClientRequest": {
        "initialize",
        "thread/start",
        "thread/resume",
        "thread/list",
        "thread/turns/list",
        "thread/settings/update",
        "model/list",
        "turn/start",
        "turn/steer",
        "turn/interrupt",
    },
    "ServerNotification": {
        "thread/started",
        "thread/settings/updated",
        "turn/started",
        "turn/completed",
        "item/started",
        "item/completed",
        "item/agentMessage/delta",
        "item/reasoning/textDelta",
        "item/reasoning/summaryTextDelta",
        "item/commandExecution/outputDelta",
    },
    "ServerRequest": {
        "item/commandExecution/requestApproval",
        "item/fileChange/requestApproval",
        "item/permissions/requestApproval",
        "item/tool/requestUserInput",
        "mcpServer/elicitation/request",
    },
}
ITEM_FIELDS = {
    "reasoning": {"id", "content", "summary"},
    "commandExecution": {"id", "command", "cwd", "aggregatedOutput", "exitCode", "durationMs"},
    "agentMessage": {"id", "text", "phase"},
}
ANNOTATIONS = {"$schema", "title", "description", "default", "examples", "deprecated"}


def structural(node, document, seen=()):
    """Resolve local references so changes behind a $ref are detected too."""
    if isinstance(node, list):
        return [structural(value, document, seen) for value in node]
    if not isinstance(node, dict):
        return node
    result = {}
    for key, value in node.items():
        if key in ANNOTATIONS or key in {"definitions", "$defs"}:
            continue
        if key == "$ref":
            if not value.startswith("#/"):
                raise ValueError(f"Unsupported external schema reference: {value}")
            if value in seen:
                result[key] = value
            else:
                target = document
                for part in value[2:].split("/"):
                    target = target[part.replace("~1", "/").replace("~0", "~")]
                result["resolved"] = structural(target, document, (*seen, value))
        else:
            normalized = structural(value, document, seen)
            if key in {"required", "enum", "type", "oneOf", "anyOf", "allOf"} and isinstance(
                normalized, list
            ):
                normalized = sorted(normalized, key=lambda x: json.dumps(x, sort_keys=True))
            result[key] = normalized
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def read_schema(root, name):
    for path in (root / "v2" / f"{name}.json", root / "v1" / f"{name}.json", root / f"{name}.json"):
        if path.exists():
            return json.loads(path.read_text())
    raise ValueError(f"Missing schema: {name}")


def field_contract(name, node, document, fields):
    properties = node.get("properties", {})
    if missing := fields - properties.keys():
        raise ValueError(f"{name}: missing fields {sorted(missing)}")
    return {
        "required": sorted(node.get("required", [])),
        "fields": {field: structural(properties[field], document) for field in sorted(fields)},
    }


def snapshot(root):
    contract = {}
    for name, fields in CONTRACT.items():
        document = read_schema(root, name)
        contract[name] = field_contract(name, document, document, fields)
    for schema, definition, fields in (
        (
            "ThreadSettingsUpdatedNotification",
            "ThreadSettings",
            {
                "model",
                "effort",
                "approvalPolicy",
                "approvalsReviewer",
                "activePermissionProfile",
                "sandboxPolicy",
            },
        ),
        (
            "ModelListResponse",
            "Model",
            {
                "model",
                "displayName",
                "description",
                "hidden",
                "defaultReasoningEffort",
                "supportedReasoningEfforts",
            },
        ),
    ):
        document = read_schema(root, schema)
        contract[definition] = field_contract(
            definition, document["definitions"][definition], document, fields
        )
    item = read_schema(root, "ItemStartedNotification")
    variants = item["definitions"]["ThreadItem"]["oneOf"]
    for kind, fields in ITEM_FIELDS.items():
        variant = next(
            (v for v in variants if v.get("properties", {}).get("type", {}).get("enum") == [kind]),
            None,
        )
        if variant is None:
            raise ValueError(f"Missing ThreadItem variant: {kind}")
        contract[f"ThreadItem.{kind}"] = field_contract(kind, variant, item, fields)
    for envelope, methods in METHODS.items():
        document = read_schema(root, envelope)
        available = {
            method
            for v in document["oneOf"]
            for method in v.get("properties", {}).get("method", {}).get("enum", [])
        }
        if missing := methods - available:
            raise ValueError(f"{envelope}: missing methods {sorted(missing)}")
    return contract


def compare(baseline, candidate):
    changes = []
    for name, before in baseline.items():
        after = candidate.get(name)
        if after is None:
            changes.append(f"{name}: removed")
            continue
        # Request/approval reply producers cannot supply newly required fields.
        if name.endswith(
            ("Params", "ApprovalResponse", "UserInputResponse", "ElicitationRequestResponse")
        ):
            if added := set(after["required"]) - set(before["required"]):
                changes.append(f"{name}: new required fields {sorted(added)}")
        else:
            if (
                optional := (set(before["required"]) - set(after["required"]))
                & before["fields"].keys()
            ):
                changes.append(f"{name}: consumed fields became optional {sorted(optional)}")
        for field, shape in before["fields"].items():
            if shape != after["fields"].get(field):
                changes.append(f"{name}.{field}: schema changed (review type/enum/constraints)")
        if added := after["fields"].keys() - before["fields"].keys():
            changes.append(f"{name}: unreviewed field coverage {sorted(added)}")
    for name in candidate.keys() - baseline.keys():
        changes.append(f"{name}: unreviewed schema coverage")
    return changes


def check(binary, baseline_path, env=None):
    version = subprocess.check_output([binary, "--version"], text=True, timeout=30, env=env).strip()
    with tempfile.TemporaryDirectory(prefix="prism-schema-") as temp:
        subprocess.run(
            [binary, "app-server", "generate-json-schema", "--experimental", "--out", temp],
            check=True,
            timeout=120,
            env=env,
            capture_output=True,
            text=True,
        )
        contract = snapshot(Path(temp))
    baseline = json.loads(baseline_path.read_text())
    changes = compare(baseline["contract"], contract)
    return {
        "codex": version,
        "result": "review_required" if changes else "structural_checks_passed",
        "baseline_codex": baseline["codex"],
        "baseline_sha256": fingerprint(baseline),
        "contract_sha256": fingerprint(contract),
        "changes": changes,
        "model_validation": "not_run",
    }, contract


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--codex", default="codex")
    p.add_argument("--baseline", type=Path, default=ROOT / "docs/protocol-baseline.json")
    p.add_argument("--report", type=Path)
    p.add_argument(
        "--write", action="store_true", help="Write docs/compatibility.json after checks"
    )
    p.add_argument(
        "--capture-baseline",
        action="store_true",
        help="Explicitly replace reviewed baseline; never used by CI",
    )
    args = p.parse_args()
    if args.capture_baseline:
        with tempfile.TemporaryDirectory(prefix="prism-baseline-") as temp:
            subprocess.run(
                [args.codex, "app-server", "generate-json-schema", "--experimental", "--out", temp],
                check=True,
                timeout=120,
            )
            contract = snapshot(Path(temp))
        version = subprocess.check_output([args.codex, "--version"], text=True, timeout=30).strip()
        args.baseline.write_text(
            json.dumps({"codex": version, "contract": contract}, indent=2) + "\n"
        )
        print(f"Baseline recorded: {args.baseline}; review and commit its diff.")
        return
    report, _ = check(args.codex, args.baseline)
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    if report["changes"]:
        raise SystemExit(1)
    if args.write:
        (ROOT / "docs/compatibility.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
