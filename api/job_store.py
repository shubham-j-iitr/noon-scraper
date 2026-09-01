"""Small file-backed job store for the first public MVP.

It deliberately avoids a database dependency. Each job is a JSON document and
results are written to the output directory. For higher scale, replace this
module with PostgreSQL + Redis/RQ without changing the API contract.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("JOB_DATA_DIR", ROOT / "data"))
JOBS_DIR = DATA_DIR / "jobs"
JOBS_DIR.mkdir(parents=True, exist_ok=True)
_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def create_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    job = {
        "job_id": job_id,
        "status": "queued",
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "progress": 0,
        "products_found": 0,
        "error": None,
        "result": None,
        "request": payload,
    }
    save_job(job)
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    path = _path(job_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_job(job: dict[str, Any]) -> None:
    job["updated_at"] = utc_now()
    path = _path(job["job_id"])
    tmp = path.with_suffix(".tmp")
    with _LOCK:
        tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)


def update_job(job_id: str, **changes: Any) -> dict[str, Any] | None:
    job = get_job(job_id)
    if not job:
        return None
    job.update(changes)
    save_job(job)
    return job
