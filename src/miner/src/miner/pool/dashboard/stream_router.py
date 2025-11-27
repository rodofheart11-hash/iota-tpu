"""Stream router for intercepting stdout/stderr."""

import asyncio
import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Queue


class StreamRouter(io.TextIOBase):
    """Intercept stdout/stderr and forward complete lines to the dashboard queue."""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop,
        queue: "Queue[str]",
        original: io.TextIOBase | None,
        mirror: bool,
    ) -> None:
        super().__init__()
        self._loop = loop
        self._queue = queue
        self._original = original
        self._mirror = mirror
        self._buffer = ""

    def writable(self) -> bool:  # pragma: no cover - io compatibility shim
        return True

    def write(self, data: str) -> int:
        if not data:
            return 0
        if self._mirror and self._original is not None:
            self._original.write(data)
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._enqueue(line)
        return len(data)

    def flush(self) -> None:
        if self._buffer:
            self._enqueue(self._buffer)
            self._buffer = ""
        if self._mirror and self._original is not None:
            self._original.flush()

    def _enqueue(self, line: str) -> None:
        if self._loop.is_closed():
            return

        def _put() -> None:
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            self._queue.put_nowait(line)

        self._loop.call_soon_threadsafe(_put)

    def __getattr__(self, name: str):  # pragma: no cover - passthrough
        if self._original is None:
            raise AttributeError(name)
        return getattr(self._original, name)
