# Completely free GitHub-only deployment

If you do not want a server bill at all, you can avoid a 24/7 web server.

Use:

**GitHub Pages → public form → GitHub Issue → GitHub Actions → Chrome → Excel committed to the repository**

GitHub documents standard GitHub-hosted Actions runners as free for public repositories. This is an on-demand runner, not a permanent server.

## User flow

1. User opens the GitHub Pages site.
2. They enter keywords, region and product limit.
3. The page opens a pre-filled GitHub issue.
4. User submits the issue.
5. The `scrape.yml` workflow starts automatically.
6. Ubuntu runner opens headless Chrome.
7. Chrome opens Noon's native search page directly and scrolls it to lazy-load products.
8. Noon product links are collected.
9. Product pages are visited and Excel is generated.
10. The workflow commits the Excel file to `public-results/` and comments the download link on the issue.

## Important tradeoff

This is free, but it is not a normal always-on SaaS backend. Each request consumes a GitHub Actions run and the result becomes public in the repository. Keep the repository public and do not put credentials in it.

For a cleaner private-result SaaS later, move the worker to a paid or appropriately provisioned service.
