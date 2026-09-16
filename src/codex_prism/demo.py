"""Hand-authored demonstration data; never presented as an actual model run."""

from .model import Trace


def demo_trace() -> Trace:
    trace = Trace()
    trace.model = "DEMO · synthetic fixtures"
    trace.cwd = "~/projects/atlas"
    trace.thread_id = "demo-session"
    items = [
        {
            "type": "userMessage",
            "id": "demo-user",
            "content": [
                {
                    "type": "text",
                    "text": "Find why the API tests fail, fix the issue, and run the focused checks.",
                }
            ],
        },
        {
            "type": "reasoning",
            "id": "demo-reasoning",
            "content": [
                "**Check the failing boundary**\n\nThe next check is the API test and its response fixture. Compare the expected status and payload before changing the handler.\n\n`rg` will locate the assertion; the focused test will confirm the observed failure."
            ],
            "summary": [
                "Inspect the failing test and response contract, then validate the fix with the focused suite."
            ],
        },
        {
            "type": "commandExecution",
            "id": "demo-search",
            "command": "rg --line-number --context 3 'status_code|response.json' tests/api/test_projects.py",
            "cwd": "/home/you/projects/atlas",
            "aggregatedOutput": "18-    response = client.get('/api/projects')\n19:    assert response.status_code == 200\n20:    assert response.json() == {'projects': []}\n21-\n22-def test_create_project(client):\n23-    response = client.post('/api/projects', json={'name': 'Atlas'})\n24:    assert response.status_code == 201\n25:    assert response.json()['name'] == 'Atlas'\n",
            "exitCode": 0,
            "durationMs": 42,
            "status": "completed",
        },
        {
            "type": "agentMessage",
            "id": "demo-commentary",
            "phase": "commentary",
            "text": "The empty-list response uses the wrong envelope. I’ll update that response and rerun the API tests.",
        },
        {
            "type": "fileChange",
            "id": "demo-patch",
            "status": "completed",
            "changes": [
                {
                    "path": "src/api/projects.py",
                    "diff": "--- a/src/api/projects.py\n+++ b/src/api/projects.py\n@@ -18,2 +18,2 @@\n def list_projects():\n-    return []\n+    return {'projects': []}",
                }
            ],
        },
        {
            "type": "commandExecution",
            "id": "demo-tests",
            "command": "python -m pytest tests/api/test_projects.py -v --tb=short",
            "cwd": "/home/you/projects/atlas",
            "aggregatedOutput": "================ test session starts ================\nplatform linux -- Python 3.12.13, pytest-8.4.2\ncollected 24 items\n\n"
            + "\n".join(
                f"tests/api/test_projects.py::test_case_{i:02d} PASSED [{i * 100 // 24:3d}%]"
                for i in range(1, 25)
            )
            + "\n\n================ 24 passed in 0.84s =================\n",
            "exitCode": 0,
            "durationMs": 1060,
            "status": "completed",
        },
        {
            "type": "agentMessage",
            "id": "demo-answer",
            "phase": "final_answer",
            "text": "Fixed the empty-projects response in `src/api/projects.py`.\n\nThe endpoint now returns `{'projects': []}`, matching the API contract. All **24 focused tests pass**.",
        },
    ]
    for item in items:
        trace.item(item, "demo-turn", True)
    trace.status = "demo"
    return trace
