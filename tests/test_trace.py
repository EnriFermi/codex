import gzip
import json

from codex_prism.model import Trace
from codex_prism.storage import Journal, export_markdown, replay


def event(method, **params):
    return {"method": method, "params": params}


def test_stream_retains_full_output_when_final_snapshot_is_clipped():
    t = Trace()
    command = "python - <<'PY'\nprint('a' * 100000)\nPY"
    t.reduce(
        event("item/started", item={"id": "c", "type": "commandExecution", "command": command})
    )
    output = "first\n" + "x" * 100000 + "\nlast\n"
    for part in [output[:44000], output[44000:]]:
        t.reduce(event("item/commandExecution/outputDelta", itemId="c", delta=part))
    t.reduce(
        event(
            "item/completed",
            item={
                "id": "c",
                "type": "commandExecution",
                "command": command,
                "aggregatedOutput": "first\n[output truncated]",
                "exitCode": 0,
            },
        )
    )
    assert t.entries["c"].output == output
    assert t.entries["c"].command == command
    assert output in export_markdown(t)


def test_summary_and_content_are_separate_and_parts_ordered():
    t = Trace()
    t.reduce(event("item/reasoning/summaryTextDelta", itemId="r", summaryIndex=0, delta="Summary."))
    t.reduce(event("item/reasoning/textDelta", itemId="r", contentIndex=1, delta="Second."))
    t.reduce(event("item/reasoning/textDelta", itemId="r", contentIndex=0, delta="First."))
    t.reduce(
        event(
            "item/completed",
            item={"id": "r", "type": "reasoning", "summary": ["Summary."], "content": []},
        )
    )
    assert t.entries["r"].content_text == "First.\n\nSecond."
    assert t.entries["r"].summary_text == "Summary."
    assert len(t.entries) == 1


def test_completed_authoritative_message_replaces_delta_without_duplication():
    t = Trace()
    t.reduce(event("item/agentMessage/delta", itemId="a", delta="Hello"))
    t.reduce(
        event(
            "item/completed",
            item={"id": "a", "type": "agentMessage", "phase": "commentary", "text": "Hello world"},
        )
    )
    assert t.entries["a"].text == "Hello world"
    assert t.entries["a"].kind == "commentary"


def test_recording_round_trip(tmp_path):
    j = Journal(tmp_path)
    message = event(
        "item/completed",
        item={
            "id": "c",
            "type": "commandExecution",
            "command": "printf 'привет\\n'",
            "aggregatedOutput": "привет\n",
            "exitCode": 0,
        },
    )
    j.write({"method": "turn/start", "params": {"input": []}}, "client")
    j.write(message)
    j.close()
    assert j.path.stat().st_mode & 0o777 == 0o600
    t = replay(j.path)
    assert t.entries["c"].output == "привет\n"
    with gzip.open(j.path, "rt") as f:
        assert json.loads(f.readlines()[1])["message"] == message


def test_export_handles_embedded_fences():
    t = Trace()
    t.item(
        {
            "id": "c",
            "type": "commandExecution",
            "command": "cat <<'EOF'\n```bash\nhi\n```\nEOF",
            "aggregatedOutput": "```\n",
        },
        complete=True,
    )
    result = export_markdown(t)
    assert "````bash\ncat" in result
    assert "````\n```\n" in result
