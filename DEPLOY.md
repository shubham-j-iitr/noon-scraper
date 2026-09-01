# Deploy for free on Render

## 1. Push the repository to GitHub

Do not commit `.env`, credentials, cookies, browser profiles, or generated Excel files.

## 2. Create Render service

1. Create a free Render account.
2. New → Web Service.
3. Connect the GitHub repository.
4. Choose Docker.
5. Choose the Free instance.
6. Render will use the included Dockerfile.
7. Set environment variables:

```text
SCRAPER_ENABLED=false
DEFAULT_HEADLESS=true
SEARCH_PAGE_INITIAL_DELAY_MIN=2
SEARCH_PAGE_INITIAL_DELAY_MAX=3
CORS_ORIGINS=*
```

8. Deploy.

## 3. Test

Open the Render URL and first verify `/health`.

Do not turn on `SCRAPER_ENABLED` until you have confirmed that your automated use of the target product site is authorized.

## 4. If authorized

Change only:

```text
SCRAPER_ENABLED=true
```

Then redeploy.

## Free-tier limitations

Render Free web services sleep after 15 minutes without inbound traffic and wake on the next request. Local files are lost on restart/redeploy/spindown, so Excel files are temporary. The app intentionally runs one Chrome job at a time.
