from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Iterable, Sequence

from utils.settings import CONFIG, SFTP_CONFIG

# Cron job call signature.
CronJob = Callable[..., None]

_UPLOAD_JOB: Sequence[str] = (
    "upload_emails_to_sftp",
    "upload_incomplete_verifications_to_sftp",
    "upload_departed_to_sftp",
    "send_survey_messages",
    "refresh_salesforce_roles",
)
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
        raise_on_error: bool = True,
    ) -> bool:
        """Run the requested cron jobs, returning True on success."""

        failures: list[str] = []

        for name, job in self._resolve_jobs(job_names):
            self._logger.info("Running cron job: %s", name)
            try:
                job()
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
        thread_name: str = "cron-scheduler",
    ) -> bool:
        """Start a background time-of-day scheduler thread for the given jobs."""

        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return False

        job_tuple = tuple(job_names)
        self._stop_event.clear()
        self._scheduler_thread = threading.Thread(
            target=self._cron_loop,
            args=(job_tuple,),
            name=thread_name,
            daemon=True,
        )
        self._scheduler_thread.start()
        self._logger.info(
            "Started %s for jobs %s (time-of-day scheduling, AZ time)",
            thread_name,
            ", ".join(job_tuple),
        )
        return True

    def stop_scheduler(self, timeout: float = 5.0) -> None:
        """Stop the active scheduler thread, if any."""

        if not self._scheduler_thread:
            return

        self._stop_event.set()
        self._scheduler_thread.join(timeout=timeout)
        self._scheduler_thread = None

    def _cron_loop(self, job_names: tuple[str, ...]) -> None:
        """Poll every 30 s; fire each job at its configured AZ hour:minute once per day."""
        from zoneinfo import ZoneInfo
        from utils.database import CronJobConfig, session_scope

        AZ_TZ = ZoneInfo("America/Phoenix")

        while not self._stop_event.is_set():
            now_az = datetime.now(AZ_TZ)

            for job_name in job_names:
                try:
                    with session_scope() as db_session:
                        cfg = (
                            db_session.query(CronJobConfig)
                            .filter(CronJobConfig.job_name == job_name)
                            .one_or_none()
                        )

                    if cfg is None or not cfg.enabled:
                        continue

                    if now_az.hour != cfg.schedule_hour or now_az.minute != cfg.schedule_minute:
                        continue

                    # Skip if already ran today (AZ date).
                    if cfg.last_run_at is not None:
                        last_az = cfg.last_run_at.replace(tzinfo=timezone.utc).astimezone(AZ_TZ)
                        if last_az.date() >= now_az.date():
                            continue

                    self.run_jobs(job_names=[job_name], raise_on_error=False)

                except Exception:
                    self._logger.exception("Scheduler tick failed for job: %s", job_name)

            if self._stop_event.wait(30):
                break


def start_upload_scheduler(cron_manager: "CronManager") -> bool:
    """Start the time-of-day scheduler for all cron jobs."""
    if CONFIG.DEV_MODE:
        logger.info("FORKLIFT_DEV_MODE enabled; skipping cron scheduler")
        return False

    return cron_manager.start_scheduler(
        job_names=_UPLOAD_JOB,
        thread_name="cron-scheduler",
    )


def stop_upload_scheduler(cron_manager: "CronManager", *, timeout: float = 5.0) -> None:
    """Stop the upload scheduler."""
    cron_manager.stop_scheduler(timeout=timeout)


__all__ = [
    "CronJob",
    "CronManager",
    "start_upload_scheduler",
    "stop_upload_scheduler",
]
