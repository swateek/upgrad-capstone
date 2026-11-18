"""Conversation lifetime (plan §7, SPEC §12): a thread's state is purged SESSION_TTL_S after its
last message. Last-seen times live next to the checkpointer, so a restart doesn't orphan
threads; the purge runs at most once a minute, on requests."""

from __future__ import annotations

import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path


class Sessions:
    def __init__(self, path: Path, ttl_s: int, delete_thread: Callable[[str], None],
                 clock=time.time) -> None:  # fmt: skip
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS sessions (thread_id TEXT PRIMARY KEY, "
                        "last_seen REAL NOT NULL)")  # fmt: skip
        self.db.commit()
        self.ttl = ttl_s
        self.delete_thread = delete_thread
        self.clock = clock
        self.lock = threading.Lock()
        self.last_purge = 0.0

    def touch(self, thread_id: str) -> None:
        with self.lock:
            self.db.execute("INSERT INTO sessions VALUES (?, ?) ON CONFLICT(thread_id) DO UPDATE "
                            "SET last_seen = excluded.last_seen", (thread_id, self.clock()))  # fmt: skip
            self.db.commit()

    def known(self, thread_id: str) -> bool:
        with self.lock:
            row = self.db.execute("SELECT last_seen FROM sessions WHERE thread_id = ?",
                                  (thread_id,)).fetchone()  # fmt: skip
        return row is not None and row[0] >= self.clock() - self.ttl

    def purge(self, force: bool = False) -> list[str]:
        now = self.clock()
        if not force and now - self.last_purge < 60:
            return []
        self.last_purge = now
        with self.lock:
            old = [r[0] for r in self.db.execute(
                "SELECT thread_id FROM sessions WHERE last_seen < ?", (now - self.ttl,))]  # fmt: skip
            for t in old:
                self.delete_thread(t)
                self.db.execute("DELETE FROM sessions WHERE thread_id = ?", (t,))
            self.db.commit()
        return old
