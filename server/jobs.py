"""Minimal background jobs, for work that takes longer than a request (OCR).

One thread per job, state in a dict. The client polls `/api/job/{id}`. Jobs are
forgotten after an hour; nothing here is persisted.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Callable, Optional

_JOBS: dict[str, "Job"] = {}
_LOCK = threading.Lock()
TTL = 3600


class Job:
    def __init__(self, kind: str):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.state = "queued"          # queued | running | done | error
        self.done = 0
        self.total = 0
        self.stage = ""
        self.result: dict[str, Any] = {}
        self.error: Optional[dict] = None   # {"key": ..., "msg": ...}
        self.started = time.time()
        self.finished = 0.0

    def progress(self, done: int, total: int, stage: str = "") -> None:
        self.done, self.total = done, total
        if stage:
            self.stage = stage

    def as_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "state": self.state,
                "done": self.done, "total": self.total, "stage": self.stage,
                "result": self.result, "error": self.error}


def _reap() -> None:
    now = time.time()
    for jid in [j for j, job in _JOBS.items()
                if job.finished and now - job.finished > TTL]:
        _JOBS.pop(jid, None)


def start(kind: str, fn: Callable[[Job], dict]) -> Job:
    job = Job(kind)
    with _LOCK:
        _reap()
        _JOBS[job.id] = job

    def run() -> None:
        job.state = "running"
        try:
            job.result = fn(job) or {}
            job.state = "done"
        except Exception as exc:  # noqa: BLE001
            # an exception may name its own i18n key (`key`), or just a code
            code = getattr(exc, "code", "")
            key = getattr(exc, "key", "") or (f"err.{kind}_{code}" if code
                                              else f"err.{kind}_failed")
            job.error = {"key": key, "msg": str(exc)}
            job.state = "error"
        finally:
            job.finished = time.time()

    threading.Thread(target=run, name=f"job-{job.id}", daemon=True).start()
    return job


def get(job_id: str) -> Optional[Job]:
    return _JOBS.get(job_id)
