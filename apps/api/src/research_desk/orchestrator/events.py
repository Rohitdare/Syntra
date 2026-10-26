"""Job events bus with database persistence and real-time subscriber fan-out.

Per docs/02-DESIGN-DOC.md Section 13.10 and docs/05-API-SPEC.md Section 3.
"""

from __future__ import annotations

import asyncio
import datetime
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from research_desk.stores.db import DbSessionFactory
from research_desk.stores.repos.jobs import JobRepo


@dataclass(frozen=True)
class EventMessage:
    """Streamable job event message matching NDJSON contract."""

    job_id: uuid.UUID
    seq: int
    ts: datetime.datetime
    stage: str
    agent: str
    type: str
    message: str | None = None
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert message to wire dict."""
        res: dict[str, Any] = {
            "seq": self.seq,
            "ts": self.ts.isoformat(),
            "stage": self.stage,
            "agent": self.agent,
            "type": self.type,
        }
        if self.message is not None:
            res["message"] = self.message
        if self.data is not None:
            res["data"] = self.data
        return res


class EventSink:
    """Persists events to PostgreSQL and fans out to active streaming subscribers."""

    def __init__(self, sessionmaker: DbSessionFactory) -> None:
        self.sessionmaker = sessionmaker
        # Active in-memory queues per job_id
        self._subscribers: dict[uuid.UUID, list[asyncio.Queue[EventMessage]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def emit(
        self,
        job_id: uuid.UUID,
        stage: str,
        agent: str,
        type_: str,
        message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> EventMessage:
        """Persist event to database and broadcast to in-memory subscriber queues."""
        async with self.sessionmaker() as session:
            async with session.begin():
                repo = JobRepo(session)
                row = await repo.add_event(
                    job_id=job_id,
                    stage=stage,
                    agent=agent,
                    type_=type_,
                    message=message,
                    data=data,
                )
                msg = EventMessage(
                    job_id=row.job_id,
                    seq=row.seq,
                    ts=row.ts,
                    stage=row.stage,
                    agent=row.agent,
                    type=row.type,
                    message=row.message,
                    data=row.data,
                )

        # Fan-out to in-memory subscriber queues
        async with self._lock:
            queues = list(self._subscribers.get(job_id, []))

        for q in queues:
            await q.put(msg)

        return msg

    async def subscribe(
        self, job_id: uuid.UUID, since_seq: int = 0
    ) -> AsyncGenerator[EventMessage, None]:
        """Subscribe to a job's event stream.

        First replays historical events from DB with seq > since_seq,
        then streams live events from memory until stage_end.
        """
        queue: asyncio.Queue[EventMessage] = asyncio.Queue()

        async with self._lock:
            self._subscribers[job_id].append(queue)

        last_seq = since_seq

        try:
            # 1. Replay historical events from PostgreSQL
            async with self.sessionmaker() as session:
                repo = JobRepo(session)
                historical = await repo.get_events(job_id, since_seq=since_seq)
                for h in historical:
                    msg = EventMessage(
                        job_id=h.job_id,
                        seq=h.seq,
                        ts=h.ts,
                        stage=h.stage,
                        agent=h.agent,
                        type=h.type,
                        message=h.message,
                        data=h.data,
                    )
                    last_seq = max(last_seq, msg.seq)
                    yield msg
                    if msg.type == "stage_end":
                        return

            # 2. Yield live events
            while True:
                msg = await queue.get()
                if msg.seq <= last_seq:
                    continue
                last_seq = msg.seq
                yield msg
                if msg.type == "stage_end":
                    break

        finally:
            async with self._lock:
                if job_id in self._subscribers and queue in self._subscribers[job_id]:
                    self._subscribers[job_id].remove(queue)
                    if not self._subscribers[job_id]:
                        del self._subscribers[job_id]
