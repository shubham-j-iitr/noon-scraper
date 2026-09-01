"""Background job runner.

The MVP uses one in-process worker to keep deployment simple. This prevents
multiple Chrome instances from being launched accidentally. For larger scale,
move this function to a dedicated RQ/Celery worker process.
"""
from __future__ import annotations

import logging
import os
import threading
import traceback
from pathlib import Path

from api.job_store import update_job
from excel_exporter import ExcelExporter
from noon_scraper import NoonScraper

logger = logging.getLogger(__name__)
_WORKER_LOCK = threading.Lock()


def _regions(region: str) -> list[str]:
    return ["uae", "ksa"] if region == "both" else [region]


def run_job(job_id: str, request: dict) -> None:
    if not _WORKER_LOCK.acquire(blocking=False):
        # The API currently only supports one browser job at a time.
        update_job(job_id, status="failed", error="Another scrape job is already running. Please try again later.")
        return

    try:
        update_job(job_id, status="running", progress=1)
        all_data = []
        regions = _regions(request["region"])
        total_steps = max(1, len(regions) * len(request["keywords"]))
        completed_steps = 0
        proxy = os.getenv("NOON_PROXY") or None

        for region in regions:
            scraper = NoonScraper(
                headless=request.get("headless", True),
                region=region,
                proxy=proxy,
            )
            try:
                for keyword in request["keywords"]:
                    logger.info("Job %s: scraping %s / %s", job_id, region, keyword)
                    data = scraper.scrape([keyword], request["max_products"])
                    all_data.extend(data or [])
                    completed_steps += 1
                    update_job(
                        job_id,
                        progress=min(99, int(completed_steps / total_steps * 100)),
                        products_found=len(all_data),
                    )
            finally:
                scraper.close()

        if not all_data:
            raise RuntimeError("No data was scraped. Check Noon availability, selectors, geo restrictions, or proxy configuration.")

        exporter = ExcelExporter()
        excel_path = exporter.export_to_excel(all_data)
        result = {
            "rows": len(all_data),
            "excel_path": str(Path(excel_path).resolve()),
            "google_sheet_url": None,
        }

        update_job(job_id, status="completed", progress=100, products_found=len(all_data), result=result)
    except Exception as exc:
        logger.exception("Job %s failed", job_id)
        update_job(job_id, status="failed", error=f"{exc}\n\n{traceback.format_exc()}")
    finally:
        _WORKER_LOCK.release()
