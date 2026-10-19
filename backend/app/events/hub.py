"""WebSocket fan-out. Each client gets a bounded queue so one slow dashboard cannot stall others."""
from __future__ import annotations

import asyncio


class Hub:
    def __init__(self, queue_size: int = 200):
        self._subs: set[asyncio.Queue] = set()
        self._size = queue_size

    @property
    def client_count(self) -> int:
        return len(self._subs)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=self._size)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    def publish(self, message: dict) -> None:
        """Must be called on the event-loop thread."""
        for q in list(self._subs):
            if q.full():
                try:
                    q.get_nowait()  # drop oldest; the client re-syncs via REST snapshot on reconnect
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(message)

    def broadcast_sync(self, message: dict, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Thread-safe publish from worker threads."""
        if loop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(self.publish, message)
                return
            except RuntimeError:
                pass
        self.publish(message)
