"""Durable local worker supervisor: ``python -m irrivise_api.worker``.

* Claims queued jobs atomically from SQLite and runs each in a separate child
  process (spawn), so training never blocks simulations and a stuck job can be
  terminated without killing the supervisor.
* Concurrency caps: ``IRRIVISE_MAX_PARALLEL_TRAINING`` (default 1) and
  ``IRRIVISE_MAX_PARALLEL_JOBS`` (default 2) for other kinds.
* Heartbeats running jobs; jobs whose heartbeat stops are marked
  ``interrupted`` (never silently resumed). Cancellation is cooperative first;
  after a grace period the child is terminated and the job marked cancelled.
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import signal
import socket
import time
import uuid

from ..config import get_settings
from ..db.models import Job, WorkerHeartbeat, utcnow
from ..db.session import migrate, session_scope
from ..services import jobs
from .tasks import execute

log = logging.getLogger("irrivise.worker")


class Supervisor:
    def __init__(self, poll_s: float = 0.5):
        self.settings = get_settings()
        self.worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.poll_s = poll_s
        self.children: dict[str, tuple[mp.Process, str, float | None]] = {}
        self.stopping = False
        self.ctx = mp.get_context("spawn")

    def heartbeat(self) -> None:
        with session_scope() as s:
            beat = s.get(WorkerHeartbeat, self.worker_id)
            if not beat:
                beat = WorkerHeartbeat(worker_id=self.worker_id, pid=os.getpid())
                s.add(beat)
            beat.last_seen = utcnow()
            beat.running_jobs = len(self.children)
            for job_id in self.children:
                job = s.get(Job, job_id)
                if job and job.status == "running":
                    job.heartbeat_at = utcnow()

    def capacity(self) -> tuple[str, ...]:
        running = [kind for _, kind, _ in self.children.values()]
        kinds = []
        if running.count("training") < self.settings.max_parallel_training:
            kinds.append("training")
        if sum(1 for k in running if k != "training") < self.settings.max_parallel_other:
            kinds += ["weather_fetch", "simulation", "experiment"]
        return tuple(kinds)

    def reap(self) -> None:
        for job_id, (proc, kind, cancel_since) in list(self.children.items()):
            with session_scope() as s:
                job = s.get(Job, job_id)
                if proc.is_alive():
                    if job.cancel_requested:
                        if cancel_since is None:
                            self.children[job_id] = (proc, kind, time.monotonic())
                        elif time.monotonic() - cancel_since > self.settings.cancel_grace_s:
                            log.warning("terminating job %s after cancel grace period", job_id)
                            proc.terminate()
                            proc.join(5)
                            if job.status == "running":
                                jobs.transition(s, job, "cancelled", "cancelled", message="Terminated after cooperative cancellation timed out; partial artifacts discarded")
                    continue
                proc.join(0)
                if job.status == "running":  # child died without recording a terminal state
                    jobs.transition(s, job, "failed" if proc.exitcode not in (0, None) else "interrupted", "crashed",
                                    error=f"Worker child exited with code {proc.exitcode} before recording completion")
            self.children.pop(job_id, None)

    def run(self) -> None:
        migrate()
        with session_scope() as s:
            stale = jobs.recover_stale(s, self.settings.heartbeat_timeout_s)
        if stale:
            log.warning("marked %d stale running job(s) as interrupted", len(stale))
        signal.signal(signal.SIGTERM, self._stop)
        signal.signal(signal.SIGINT, self._stop)
        last_beat = 0.0
        last_recover = time.monotonic()
        log.info("worker %s ready", self.worker_id)
        while not self.stopping:
            now = time.monotonic()
            if now - last_beat > 2:
                self.heartbeat()
                last_beat = now
            if now - last_recover > 15:
                with session_scope() as s:
                    jobs.recover_stale(s, self.settings.heartbeat_timeout_s)
                last_recover = now
            self.reap()
            kinds = self.capacity()
            claimed = None
            if kinds:
                with session_scope() as s:
                    job = jobs.claim_next(s, self.worker_id, kinds)
                    claimed = (job.id, job.kind) if job else None
            if claimed:
                proc = self.ctx.Process(target=execute, args=(claimed[0], os.getpid()), name=f"irrivise-job-{claimed[0][:8]}", daemon=False)
                proc.start()
                self.children[claimed[0]] = (proc, claimed[1], None)
                log.info("started %s job %s (pid %s)", claimed[1], claimed[0], proc.pid)
                continue
            time.sleep(self.poll_s)
        self.shutdown()

    def _stop(self, *_):
        self.stopping = True

    def shutdown(self) -> None:
        for job_id, (proc, _, _) in self.children.items():
            if proc.is_alive():
                proc.terminate()
                proc.join(5)
            with session_scope() as s:
                job = s.get(Job, job_id)
                if job and job.status == "running":
                    jobs.transition(s, job, "interrupted", "interrupted", error="Worker shut down while the job was running; re-queue to run again")
        with session_scope() as s:
            beat = s.get(WorkerHeartbeat, self.worker_id)
            if beat:
                s.delete(beat)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    Supervisor().run()


if __name__ == "__main__":
    main()
