"""JSON-RPC transport for a dedicated Codex app-server child process."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from collections.abc import Callable


class RpcError(RuntimeError):
    def __init__(self, error: dict):
        self.error = error
        super().__init__(error.get("message", str(error)))


class AppServer:
    def __init__(
        self,
        binary: str = "codex",
        overrides: list[str] | None = None,
        on_message: Callable[[dict], None] | None = None,
        on_sent: Callable[[dict], None] | None = None,
    ):
        self.binary = binary
        self.overrides = overrides or []
        self.on_message = on_message or (lambda _: None)
        self.on_sent = on_sent or (lambda _: None)
        self.process: asyncio.subprocess.Process | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.counter = 0
        self.tasks: list[asyncio.Task] = []
        self.stderr: deque[str] = deque(maxlen=100)
        self.closing = False
        self._write_lock = asyncio.Lock()

    async def start(self) -> dict:
        args = [self.binary, "app-server", "--listen", "stdio://"]
        for override in self.overrides:
            args.extend(["-c", override])
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=256 * 1024 * 1024,
        )
        self.tasks = [asyncio.create_task(self._read()), asyncio.create_task(self._stderr())]
        try:
            result = await self.request(
                "initialize",
                {
                    "clientInfo": {
                        "name": "codex_prism",
                        "title": "Codex Prism",
                        "version": "0.1.0",
                    },
                    "capabilities": {"experimentalApi": False},
                },
            )
            await self.send({"method": "initialized", "params": {}})
            return result
        except BaseException:
            await self.close()
            raise

    async def send(self, message: dict):
        if self.process is None or self.process.returncode is not None:
            raise ConnectionError("Codex app-server is not running")
        async with self._write_lock:
            self.process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
            await self.process.stdin.drain()
            self.on_sent(message)

    async def request(self, method: str, params: dict, timeout: float = 60) -> dict:
        self.counter += 1
        key = self.counter
        future = asyncio.get_running_loop().create_future()
        self.pending[key] = future
        try:
            await self.send({"id": key, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(key, None)

    async def respond(
        self, id: str | int, result: dict | None = None, *, error: dict | None = None
    ):
        await self.send({"id": id, **({"error": error} if error else {"result": result or {}})})

    async def _read(self):
        failure: Exception = ConnectionError("Codex app-server closed the connection")
        try:
            while line := await self.process.stdout.readline():
                try:
                    message = json.loads(line)
                except (ValueError, UnicodeError) as exc:
                    raise ConnectionError("Invalid JSON from Codex app-server") from exc
                if "id" in message and "method" not in message:
                    future = self.pending.get(message["id"])
                    if future and not future.done():
                        if "error" in message:
                            future.set_exception(RpcError(message["error"]))
                        else:
                            future.set_result(message.get("result", {}))
                else:
                    self.on_message(message)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            failure = exc
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(failure)
            if not self.closing:
                self.on_message({"method": "prism/error", "params": {"message": str(failure)}})

    async def _stderr(self):
        while line := await self.process.stderr.readline():
            self.stderr.append(line.decode(errors="replace").rstrip())

    async def close(self):
        if self.closing:
            return
        self.closing = True
        if self.process and self.process.returncode is None:
            self.process.stdin.close()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), 3)
                except TimeoutError:
                    self.process.kill()
                    await self.process.wait()
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        for future in self.pending.values():
            if not future.done():
                future.set_exception(ConnectionError("Client closed"))
