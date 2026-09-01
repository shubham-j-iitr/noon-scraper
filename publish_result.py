import os
import subprocess

issue = os.environ['ISSUE_NUMBER']
repo = os.environ.get('GITHUB_REPOSITORY', '')
server = os.environ.get('GITHUB_SERVER_URL', 'https://github.com')
run_id = os.environ.get('GITHUB_RUN_ID', '')

os.makedirs('public-results', exist_ok=True)
shutil = __import__('shutil')
shutil.copy2('output/result.xlsx', f'public-results/noon-result-{issue}.xlsx')

subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True)
subprocess.run(['git', 'add', f'public-results/noon-result-{issue}.xlsx'], check=True)
subprocess.run(['git', 'commit', '-m', f'Add scraper result for issue #{issue}'], check=True)
subprocess.run(['git', 'push'], check=True)

raw_url = f'{server}/{repo}/raw/refs/heads/main/public-results/noon-result-{issue}.xlsx'
comment = f'Scrape completed. Download the Excel result: {raw_url}\n\nWorkflow run: {server}/{repo}/actions/runs/{run_id}'
subprocess.run(['gh', 'issue', 'comment', issue, '--body', comment], check=True)
subprocess.run(['gh', 'issue', 'close', issue], check=True)
