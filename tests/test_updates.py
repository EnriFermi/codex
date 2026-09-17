"""Failure-oriented checks for the release gate; no network or model calls."""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


protocol = load_script("check_protocol")
updater = load_script("check_codex_update")


def release(version="0.154.0", **flags):
    return {
        "tag_name": f"rust-v{version}",
        "draft": False,
        "prerelease": False,
        "assets": [
            {
                "name": updater.ASSET,
                "browser_download_url": f"https://github.com/openai/codex/releases/download/rust-v{version}/{updater.ASSET}",
                "digest": "sha256:" + "a" * 64,
            }
        ],
        **flags,
    }


def test_release_selection_and_never_downgrade():
    chosen = updater.select_release(release())
    assert updater.should_check(chosen, "0.153.3", None)
    assert not updater.should_check(chosen, "0.153.3", "0.154.0")
    assert updater.should_check(chosen, "0.153.3", "0.154.0", force=True)
    assert not updater.should_check(chosen, "0.155.0", None, force=True)
    assert not updater.should_check(chosen, "0.153.3", "0.155.0", force=True)
    assert updater.version_tuple("0.100.0") > updater.version_tuple("0.99.0")


@pytest.mark.parametrize(
    "changes",
    [
        {"prerelease": True},
        {"draft": True},
        {"tag_name": "rust-v0.155.0-alpha.1"},
        {"tag_name": "other-v0.154.0"},
        {"assets": []},
    ],
)
def test_unpublished_prerelease_and_missing_packages_rejected(changes):
    with pytest.raises(ValueError):
        updater.select_release(release(**changes))


def test_asset_digest_and_url_are_mandatory():
    bad = release()
    bad["assets"][0]["digest"] = None
    with pytest.raises(ValueError):
        updater.select_release(bad)
    bad = release()
    bad["assets"][0]["browser_download_url"] = "https://example.com/untrusted.tar.gz"
    with pytest.raises(ValueError):
        updater.select_release(bad)


def test_candidate_environment_excludes_credentials(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-secret")
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setenv("CODEX_HOME", "/private/profile")
    env = updater.isolated_environment(tmp_path)
    assert "OPENAI_API_KEY" not in env and "GH_TOKEN" not in env
    assert env["CODEX_HOME"] == str(tmp_path)


def test_schema_refs_types_enums_and_required_fields():
    doc = {
        "type": "object",
        "required": ["mode"],
        "properties": {"mode": {"$ref": "#/definitions/Mode"}},
        "definitions": {"Mode": {"type": "string", "enum": ["safe", "full"]}},
    }

    def contract(value, name="ExampleParams"):
        return {name: protocol.field_contract(name, value, value, {"mode"})}

    before = contract(doc)
    optional_addition = copy.deepcopy(doc)
    optional_addition["properties"]["future"] = {"type": "integer"}
    optional_addition["definitions"]["Mode"]["description"] = "New docs"
    assert protocol.compare(before, contract(optional_addition)) == []
    optional_addition["required"].append("future")
    assert "new required fields" in protocol.compare(before, contract(optional_addition))[0]
    changed_type = copy.deepcopy(doc)
    changed_type["definitions"]["Mode"] = {"type": "integer"}
    assert protocol.compare(before, contract(changed_type))
    changed_enum = copy.deepcopy(doc)
    changed_enum["definitions"]["Mode"]["enum"].remove("safe")
    assert protocol.compare(before, contract(changed_enum))
    optional_output = copy.deepcopy(doc)
    optional_output["required"] = []
    assert protocol.compare(
        contract(doc, "OutputNotification"), contract(optional_output, "OutputNotification")
    )
    removed = copy.deepcopy(doc)
    del removed["properties"]["mode"]
    with pytest.raises(ValueError, match="missing fields"):
        contract(removed)


def test_skipped_update_removes_stale_success_report(tmp_path, monkeypatch):
    from argparse import Namespace

    (tmp_path / "candidate.json").write_text('{"stale": true}')
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"codex": "codex-cli 0.153.3"}))
    accepted = tmp_path / "accepted.json"
    accepted.write_text(json.dumps({"version": "0.154.0"}))
    monkeypatch.setattr(updater, "latest_release", lambda _: updater.select_release(release()))
    args = Namespace(
        work_dir=tmp_path, baseline=baseline, accepted=accepted, version=None, force=False
    )
    assert updater.run(args)["status"] == "skipped"
    assert not (tmp_path / "candidate.json").exists()
