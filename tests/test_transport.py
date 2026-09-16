import asyncio
from pathlib import Path

import pytest

from codex_prism.transport import AppServer, RpcError

FAKE = str(Path(__file__).with_name("fake_server.py"))


async def test_transport_large_frames_errors_and_server_requests():
    events = []
    server = AppServer(FAKE, on_message=events.append)
    try:
        assert (await server.start())["userAgent"] == "fake/1"
        assert (await server.request("test/big", {}))["ok"]
        assert len(events[0]["params"]["delta"]) == 300000
        await server.request("test/approval", {})
        assert events[-1]["id"] == "server-approval"
        await server.respond("server-approval", {"decision": "decline"})
        with pytest.raises(RpcError, match="deliberate"):
            await server.request("test/error", {})
        results = await asyncio.gather(*(server.request("test/echo", {"n": n}) for n in range(10)))
        assert [r["n"] for r in results] == list(range(10))
    finally:
        await server.close()
    assert server.process.returncode is not None


async def test_timeout_and_exit_fail_pending_requests():
    server = AppServer(FAKE)
    await server.start()
    with pytest.raises(asyncio.TimeoutError):
        await server.request("test/timeout", {}, timeout=0.05)
    assert not server.pending
    with pytest.raises(ConnectionError):
        await server.request("test/eof", {}, timeout=2)
    await server.close()
