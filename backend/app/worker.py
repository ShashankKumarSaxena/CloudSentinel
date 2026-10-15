"""Dedicated, signal-aware production worker: python -m backend.app.worker."""

from datetime import datetime, timezone
import os
import signal
import threading
import time

from backend.app.application import create_app
from backend.app.core.config import Settings


def main():
    settings = Settings.from_env()
    services = create_app(settings=settings).state.services
    if settings.live_ml_enabled and (
        not services.model.status().get("ready")
        or services.model.status().get("provenance") != "user_labeled"
    ):
        raise SystemExit("A reviewed non-synthetic model is required for live ML.")
    if not settings.production:
        services.model.ensure_default()
    stopped = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stopped.set())
    services.worker.enabled = True
    services.worker.start()
    started = time.monotonic()
    try:
        while not stopped.wait(5):
            if not services.worker.status()["running"]:
                raise SystemExit("Worker stopped unexpectedly; restart and review readiness.")
            try:
                heartbeat = services.jobs.worker_status()
                age = (
                    (
                        datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat["updated_at"])
                    ).total_seconds()
                    if heartbeat
                    else settings.worker_stale_seconds + 1
                )
            except Exception:
                # An unavailable DB also means the worker cannot safely publish.
                age = (
                    (
                        datetime.now(timezone.utc)
                        - datetime.fromisoformat(services.worker.last_tick)
                    ).total_seconds()
                    if services.worker.last_tick
                    else time.monotonic() - started
                )
            if age > settings.worker_stale_seconds:
                # A provider/DNS call may be stuck in a library thread. Exiting
                # the process releases its DB lock and lets the supervisor restart
                # and recover durable work; waiting for that thread would deadlock.
                print('{"event":"worker.watchdog_stop","reason":"stale_heartbeat"}', flush=True)
                os._exit(1)
    finally:
        services.worker.stop()
        services.store.database.close()


if __name__ == "__main__":
    main()
