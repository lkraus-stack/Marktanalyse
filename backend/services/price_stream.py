from __future__ import annotations

import asyncio
from typing import Any, Dict, Set


class PricePubSub:
    """In-process pub/sub broker for websocket price updates."""

    def __init__(self) -> None:
        self._clients: Set[asyncio.Queue[Dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def subscribe(self) -> asyncio.Queue[Dict[str, Any]]:
        """Register one websocket consumer queue."""
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._clients.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[Dict[str, Any]]) -> None:
        """Unregister one websocket consumer queue."""
        async with self._lock:
            self._clients.discard(queue)

    async def publish(self, message: Dict[str, Any]) -> None:
        """Broadcast one message to all connected consumers."""
        async with self._lock:
            clients = list(self._clients)
        for queue in clients:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                continue

    async def client_count(self) -> int:
        """Return active client count."""
        async with self._lock:
            return len(self._clients)


price_pubsub = PricePubSub()
