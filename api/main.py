from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse

from api.job_store import create_job, get_job
from api.schemas import ScrapeRequest
from api.worker import run_job
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from time import monotonic

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

app = FastAPI(title="Noon Scraper API", version="1.0.0")
_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="noon-scraper")
_RATE = defaultdict(list)
_RATE_WINDOW_SECONDS = 3600
_RATE_MAX_JOBS = 3
origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:8000").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "noon-scraper"}

@app.get("/api/config")
def public_config():
    return {
        "scraper_enabled": os.getenv("SCRAPER_ENABLED", "false").lower() == "true",
        "google_sheets_enabled": False,
        "search_provider": "direct_noon",
    }


@app.get("/", response_class=HTMLResponse)
def home():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.post("/api/jobs")
def create_scrape_job(payload: ScrapeRequest, request: Request):
    if os.getenv("SCRAPER_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=503, detail="Scraping is disabled on this deployment. Enable SCRAPER_ENABLED only after you have authorization to automate the target site.")

    # Basic public-MVP abuse control. Replace this with Redis-backed rate
    # limiting before scaling beyond a single application instance.
    client_ip = request.client.host if request.client else "unknown"
    now = monotonic()
    recent = [t for t in _RATE[client_ip] if now - t < _RATE_WINDOW_SECONDS]
    if len(recent) >= _RATE_MAX_JOBS:
        raise HTTPException(status_code=429, detail="Hourly job limit reached. Please try again later.")
    recent.append(now)
    _RATE[client_ip] = recent

    job_id = uuid.uuid4().hex
    job = create_job(job_id, payload.model_dump())
    _EXECUTOR.submit(run_job, job_id, payload.model_dump())
    return {"job_id": job_id, "status": job["status"]}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Never expose the submitted request or traceback to the browser.
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "products_found": job["products_found"],
        "error": job["error"] if job["status"] == "failed" else None,
        "result": job["result"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
    }


@app.get("/api/jobs/{job_id}/download")
def download_result(job_id: str):
    job = get_job(job_id)
    if not job or job.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Completed job not found")
    result = job.get("result") or {}
    path = Path(result.get("excel_path", ""))
    if not path.exists() or path.parent.resolve() != OUTPUT.resolve():
        raise HTTPException(status_code=404, detail="Result file not found")
    return FileResponse(path, filename=path.name, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
