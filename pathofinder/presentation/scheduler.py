"""Overnight queue build scheduling (APScheduler, in-process, no network).

The scheduled job PREPARES ingestion/extraction so the morning queue is
instant — but flags are only presented after the operator signs on with
initials, and the run itself is recorded under those initials at sign-on.
A manual "Build queue now" action calls the same entry point.
"""

from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

DEFAULT_BUILD_HOUR = 5   # 05:00 local, before the practice opens


class OvernightScheduler:
    def __init__(self, build_callable, hour: int = DEFAULT_BUILD_HOUR, minute: int = 0):
        self._scheduler = BackgroundScheduler(daemon=True)
        self._build = build_callable
        self._hour = hour
        self._minute = minute

    def start(self) -> None:
        self._scheduler.add_job(
            self._build, CronTrigger(hour=self._hour, minute=self._minute),
            id="overnight-queue-build", replace_existing=True,
            coalesce=True, max_instances=1,
        )
        self._scheduler.start()

    def trigger_now(self) -> None:
        """Manual 'Build queue now'."""
        self._build()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
