"""Cron job helpers and manager."""

from cron.manager import (
    CronManager,
    start_upload_scheduler as _start_upload_scheduler,
    stop_upload_scheduler as _stop_upload_scheduler,
)

cron_manager = CronManager()


def start_upload_scheduler() -> bool:
    return _start_upload_scheduler(cron_manager)


def stop_upload_scheduler(*, timeout: float = 5.0) -> None:
    _stop_upload_scheduler(cron_manager, timeout=timeout)


def _register_default_jobs() -> None:
    from cron import jobs

    cron_manager.register_jobs(jobs.AVAILABLE_JOBS)


_register_default_jobs()

__all__ = [
    "CronManager",
    "cron_manager",
    "start_upload_scheduler",
    "stop_upload_scheduler",
]
