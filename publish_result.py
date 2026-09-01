import base64
import json
import os
import subprocess
import urllib.request

issue = os.environ['ISSUE_NUMBER']
repo = os.environ.get('GITHUB_REPOSITORY', '')
server = os.environ.get('GITHUB_SERVER_URL', 'https://github.com')
run_id = os.environ.get('GITHUB_RUN_ID', '')
token = os.environ['GH_TOKEN']

result_path = f'public-results/noon-result-{issue}.xlsx'
os.makedirs('public-results', exist_ok=True)
shutil = __import__('shutil')
shutil.copy2('output/result.xlsx', result_path)

# Publish the binary through the GitHub Contents API instead of pushing a local
# checkout. This avoids non-fast-forward failures when GitHub Actions updates
# main concurrently with Pages or another scraper run.
api_url = f'https://api.github.com/repos/{repo}/contents/{result_path}'
with open(result_path, 'rb') as f:
    encoded = base64.b64encode(f.read()).decode('ascii')

headers = {
    'Authorization': f'Bearer {token}',
    'Accept': 'application/vnd.github+json',
    'X-GitHub-Api-Version': '2022-11-28',
    'User-Agent': 'noon-scraper-actions',
    'Content-Type': 'application/json',
}

existing_sha = None
try:
    request = urllib.request.Request(api_url, headers=headers, method='GET')
    with urllib.request.urlopen(request) as response:
        existing = json.load(response)
        existing_sha = existing.get('sha')
except urllib.error.HTTPError as exc:
    if exc.code != 404:
        raise

payload = {
    'message': f'Add scraper result for issue #{issue}',
    'content': encoded,
    'branch': 'main',
}
if existing_sha:
    payload['sha'] = existing_sha

request = urllib.request.Request(
    api_url,
    data=json.dumps(payload).encode('utf-8'),
    headers=headers,
    method='PUT',
)
with urllib.request.urlopen(request) as response:
    response.read()

raw_url = f'{server}/{repo}/raw/refs/heads/main/public-results/noon-result-{issue}.xlsx'
comment = f'Scrape completed. Download the Excel result: {raw_url}\n\nWorkflow run: {server}/{repo}/actions/runs/{run_id}'
subprocess.run(['gh', 'issue', 'comment', issue, '--body', comment], check=True)
subprocess.run(['gh', 'issue', 'close', issue], check=True)
