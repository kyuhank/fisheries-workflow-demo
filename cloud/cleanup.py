"""Remove completed, temporary demo runs; preserve CI and published releases."""
import datetime as dt
import json
import os
from urllib.request import Request, urlopen

REPO = 'kyuhank/fisheries-workflow-demo'


def api(path, method='GET'):
    request = Request('https://api.github.com/repos/' + REPO + '/' + path, method=method,
                      headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
                               'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'})
    with urlopen(request, timeout=30) as response:
        return json.load(response) if response.status != 204 else None


def main():
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=10)
    for workflow in ['live.yml', 'cleanup.yml']:
        # One request page at a time; deletion changes the listing, so collect IDs first.
        expired = []
        for page in range(1, 12):
            rows = api(f'actions/workflows/{workflow}/runs?status=completed&per_page=100&page={page}')['workflow_runs']
            expired += [row['id'] for row in rows if dt.datetime.fromisoformat(row['updated_at'].replace('Z', '+00:00')) < cutoff]
            if len(rows) < 100:
                break
        for run_id in expired:
            api('actions/runs/' + str(run_id), 'DELETE')
        print(workflow + ': removed ' + str(len(expired)) + ' expired runs')


if __name__ == '__main__':
    main()
