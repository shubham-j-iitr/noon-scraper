# Noon Scraper — Direct Noon Search Edition

A Python/Selenium web app that opens Chrome, goes directly to Noon native search URLs, scrolls the search-results page to lazy-load products, visits each Noon product page, extracts the same product/seller fields as the original scraper, and exports the results to Excel.

## No Google/Noon API

This version does not require a Google API key, Noon API, Google login, or Noon credentials. Chrome opens Noon directly using `https://www.noon.com/<region>/search/?q=<keyword>` and scrolls the native search-results page to collect product URLs.

## Important

Only use automated browsing where you are authorized to do so and comply with the applicable Google and Noon terms, robots policies and rate limits. The app does not attempt to bypass CAPTCHA or verification pages.

## Local

```bash
python -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# set SCRAPER_ENABLED=true only after confirming your use is authorized
uvicorn api.main:app --reload
```

Open http://localhost:8000.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

## Public free deployment

The recommended first free host is Render Free. Connect this GitHub repository as a Docker Web Service. Render provides a public `onrender.com` URL, free TLS, and 750 free instance hours per month. Free services sleep after 15 minutes of inactivity, so the first request after sleep can take about a minute. The filesystem is ephemeral; generated Excel files should be downloaded immediately.

For a scraper that launches Chrome, keep the concurrency at one and keep the per-job limits small.

## API endpoints (internal app endpoints, no external API keys)

- `GET /health`
- `GET /api/config`
- `POST /api/jobs`
- `GET /api/jobs/{job_id}`
- `GET /api/jobs/{job_id}/download`
