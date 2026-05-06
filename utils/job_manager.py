"""
Generic in-memory job manager for async background tasks.

Provides a thread-safe mechanism to:
  - Create jobs that run in background threads
  - Poll job status and retrieve results
  - Auto-expire completed jobs after a configurable TTL

Security notes:
  - Job IDs are UUIDs (cryptographically random, unpredictable)
  - No credentials or secrets are stored in the job store
  - Results auto-expire to minimize data retention
  - Max concurrent jobs limit prevents resource exhaustion
"""

import uuid
import threading
from datetime import datetime, timezone


# --- Configuration ---
JOB_TTL_SECONDS = 600   # 10 minutes
MAX_ACTIVE_JOBS = 5

# --- Internal State ---
_jobs = {}
_jobs_lock = threading.Lock()


def create_job(task_fn, *args, **kwargs):
    """
    Creates a background job and starts it immediately.

    The task_fn receives an `update_progress` callback as its first argument,
    followed by any additional *args and **kwargs passed here.

    The update_progress callback signature:
        update_progress(progress_text: str, **extra_fields)

    Returns:
        (job_id, error) — error is a string if the job could not be created, else None.
    """
    _cleanup_expired()

    job_id = str(uuid.uuid4())
    job = {
        "status": "pending",
        "progress": "Starting...",
        "accounts_total": 0,
        "accounts_completed": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": None,
        "error": None,
    }

    with _jobs_lock:
        active_count = sum(
            1 for j in _jobs.values() if j["status"] in ("pending", "running")
        )
        if active_count >= MAX_ACTIVE_JOBS:
            return None, "Too many active jobs. Please wait for existing jobs to complete."
        _jobs[job_id] = job

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, task_fn, args, kwargs),
        daemon=True
    )
    thread.start()

    return job_id, None


def get_job(job_id):
    """
    Returns a copy of the job state dict, or None if not found / expired.
    Triggers lazy cleanup of expired jobs.
    """
    _cleanup_expired()
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return None
        # Return a shallow copy to avoid external mutation
        return dict(job)


def _run_job(job_id, task_fn, args, kwargs):
    """Executes the task function and updates the job store on completion or failure."""

    def update_progress(progress_text, **extra):
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["progress"] = progress_text
                _jobs[job_id]["status"] = "running"
                for k, v in extra.items():
                    _jobs[job_id][k] = v

    try:
        results = task_fn(update_progress, *args, **kwargs)
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "completed"
                _jobs[job_id]["results"] = results
                _jobs[job_id]["progress"] = "Done"
    except Exception as e:
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["status"] = "failed"
                _jobs[job_id]["error"] = str(e)
                _jobs[job_id]["progress"] = "Failed"


def _cleanup_expired():
    """Removes jobs older than JOB_TTL_SECONDS."""
    now = datetime.now(timezone.utc)
    with _jobs_lock:
        expired = [
            jid for jid, job in _jobs.items()
            if (now - datetime.fromisoformat(job["created_at"])).total_seconds() > JOB_TTL_SECONDS
        ]
        for jid in expired:
            del _jobs[jid]
