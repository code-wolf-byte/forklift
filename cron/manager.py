from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterable, Sequence

from utils.settings import CONFIG, SFTP_CONFIG

# Cron job call signature. Jobs should accept **kwargs to stay flexible.
CronJob = Callable[..., None]

_UPLOAD_JOB: Sequence[str] = ("upload_emails_to_sftp",)
_UPLOAD_INTERVAL_SECONDS = 24 * 60 * 60
logger = logging.getLogger(__name__)


class CronManager:
    """Register, run, and schedule cron jobs in a single place."""

    def __init__(self) -> None:
        self._jobs: dict[str, CronJob] = {}
        self._scheduler_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._logger = logging.getLogger(__name__)

    def register_job(self, name: str, job: CronJob) -> None:
        self._jobs[name] = job

    def register_jobs(self, jobs: dict[str, CronJob]) -> None:
        for name, job in jobs.items():
            self.register_job(name, job)

    @property
    def job_names(self) -> tuple[str, ...]:
        return tuple(self._jobs.keys())

    def _resolve_jobs(
        self, job_names: Iterable[str] | None
    ) -> Sequence[tuple[str, CronJob]]:
        if job_names is None:
            return list(self._jobs.items())

        resolved: list[tuple[str, CronJob]] = []
        for name in job_names:
            job = self._jobs.get(name)
            if job is None:
                self._logger.warning("Ignoring unknown cron job: %s", name)
                continue
            resolved.append((name, job))
        return resolved

    def run_jobs(
        self,
        *,
        job_names: Iterable[str] | None = None,
        start_metadata_scheduler: bool = True,
        raise_on_error: bool = True,
    ) -> bool:
        """Run the requested cron jobs, returning True on success."""

        job_kwargs = {"start_scheduler": start_metadata_scheduler}
        failures: list[str] = []

        for name, job in self._resolve_jobs(job_names):
            self._logger.info("Running cron job: %s", name)
            try:
                job(**job_kwargs)
            except Exception:
                self._logger.exception("Cron job failed: %s", name)
                if raise_on_error:
                    raise
                failures.append(name)

        if failures:
            self._logger.error("Cron jobs failed: %s", ", ".join(failures))
        return not failures

    def start_scheduler(
        self,
        *,
        job_names: Iterable[str],
        interval_seconds: float,
        start_metadata_scheduler: bool = False,
        thread_name: str = "cron-scheduler",
    ) -> bool:
        """Start a background scheduler thread for the given jobs."""

        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return False

        job_tuple = tuple(job_names)
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._cron_loop,
            args=(job_tuple, interval_seconds, start_metadata_scheduler),
            name=thread_name,
            daemon=True,
        )
        self._scheduler_thread.start()
        self._logger.info(
            "Started %s for jobs %s (interval %.0fs)",
            thread_name,
            ", ".join(job_tuple),
            interval_seconds,
        )
        return True

    def stop_scheduler(self, timeout: float = 5.0) -> None:
        """Stop the active scheduler thread, if any."""

        if not self._scheduler_thread:
            return

        self._stop_event.set()
        self._scheduler_thread.join(timeout=timeout)
        self._scheduler_thread = None

    def _cron_loop(
        self,
        job_names: Iterable[str],
        interval_seconds: float,
        start_metadata_scheduler: bool,
    ) -> None:
        while not self._stop_event.is_set():
            start = time.monotonic()
            self.run_jobs(
                job_names=job_names,
                start_metadata_scheduler=start_metadata_scheduler,
                raise_on_error=False,
            )
            elapsed = time.monotonic() - start
            delay = max(1.0, interval_seconds - elapsed)
            if self._stop_event.wait(delay):
                break


def start_upload_scheduler(
    cron_manager: "CronManager",
    *,
    interval_seconds: float = _UPLOAD_INTERVAL_SECONDS,
) -> bool:
    """Start the daily upload_emails_to_sftp scheduler."""
    if CONFIG.DEV_MODE:
        logger.info("FORKLIFT_DEV_MODE enabled; skipping SFTP scheduler")
        return False
    if SFTP_CONFIG is None:
        logger.info("SFTP uploads not configured; skipping scheduler")
        return False

    started = cron_manager.start_scheduler(
        job_names=_UPLOAD_JOB,
        interval_seconds=interval_seconds,
        start_metadata_scheduler=False,
        thread_name="upload-emails-scheduler",
    )
    if started:
        logger.info(
            "upload_emails_to_sftp scheduler active (interval %.0fs)",
            interval_seconds,
        )
    return started


def stop_upload_scheduler(cron_manager: "CronManager", *, timeout: float = 5.0) -> None:
    """Stop the daily upload scheduler."""
    cron_manager.stop_scheduler(timeout=timeout)


__all__ = [
    "CronJob",
    "CronManager",
    "start_upload_scheduler",
    "stop_upload_scheduler",
]
