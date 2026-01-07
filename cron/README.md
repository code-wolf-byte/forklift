# Cron manager

Utilities for registering and scheduling recurring jobs.

## Components

- `CronManager` (in `cron/manager.py`): core registry and scheduler. Methods:
  - `register_job(name, callable)` / `register_jobs(dict)` to register jobs.
  - `run_jobs(job_names=None)` to run once.
  - `start_scheduler(job_names, interval_seconds, thread_name="cron-scheduler")` to launch a background loop.
  - `stop_scheduler(timeout=5.0)` to stop the background loop.
- `cron_manager` (from `cron/__init__.py`): shared instance with default jobs loaded from `cron/jobs.py` (currently `upload_emails_to_sftp`).
- `start_upload_scheduler(interval_seconds=86400)` / `stop_upload_scheduler(timeout=5.0)`: convenience wrappers that start/stop the daily `upload_emails_to_sftp` job, skipping itself when `DEV_MODE` is on or SFTP is not configured.

## Typical usage

Run a job immediately (one-shot):

```python
from cron import cron_manager

# Run all registered jobs
cron_manager.run_jobs()

# Or run a subset
cron_manager.run_jobs(job_names=("upload_emails_to_sftp",))
```

Start a background scheduler:

```python
from cron import cron_manager

cron_manager.start_scheduler(
    job_names=("upload_emails_to_sftp",),
    interval_seconds=3600,
)
```

Stop a running scheduler:

```python
from cron import cron_manager

cron_manager.stop_scheduler(timeout=5.0)
```

Start/stop the daily SFTP upload helper (preferred when SFTP uploads are enabled):

```python
from cron import start_upload_scheduler, stop_upload_scheduler

start_upload_scheduler()  # 24h interval by default
# ...
stop_upload_scheduler()
```
