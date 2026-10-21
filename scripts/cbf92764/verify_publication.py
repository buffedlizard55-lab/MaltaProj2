"""Hosted, branch-only recovery of terminal legacy Pages runs and live verification.

Never touches source branches, refresh jobs, healthy Pages jobs or publisher mode.
"""
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import subprocess

REPO = 'buffedlizard55-lab/MaltaProj2'
TARGET = '1c051608ae40ef35ca1b240be35c4ad7833c0f2c'
ROOT = Path(__file__).resolve().parents[2]


def api(path, method='GET'):
    result = subprocess.run(['gh', 'api', '-X', method, f'repos/{REPO}/{path}'],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout) if result.stdout.strip() else None


def terminal_legacy(run, jobs, now):
    """An abandoned run is not an active build: every job must already be terminal."""
    if (run.get('name') != 'pages build and deployment'
            or run.get('event') != 'dynamic'
            or run.get('status') != 'in_progress'
            or not jobs
            or any(job.get('status') != 'completed' for job in jobs)):
        return False
    created = datetime.fromisoformat(run['created_at'].replace('Z', '+00:00'))
    return (now - created).total_seconds() >= 600


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    gate = load('cbf_publication_gate', 'scripts/6ffacd40/pages_gate.py')
    assert gate.configured_publisher(api('pages')) == 'legacy'
    comparison = api(f'compare/{TARGET}...main')
    assert comparison['status'] in ('ahead', 'identical'), 'Main must contain PR196'
    runs = api('actions/runs?branch=main&status=in_progress&per_page=100')['workflow_runs']
    recovered = []
    for run in runs:
        if run.get('name') != 'pages build and deployment' or run.get('event') != 'dynamic':
            continue
        jobs = api(f"actions/runs/{run['id']}/jobs?per_page=100")['jobs']
        if terminal_legacy(run, jobs, datetime.now(timezone.utc)):
            # Re-read immediately before recovery; never cancel a newly active job.
            fresh = api(f"actions/runs/{run['id']}")
            fresh_jobs = api(f"actions/runs/{run['id']}/jobs?per_page=100")['jobs']
            if terminal_legacy(fresh, fresh_jobs, datetime.now(timezone.utc)):
                api(f"actions/runs/{run['id']}/force-cancel", 'POST')
                recovered.append(run['id'])
    print('Recovered only already-terminal legacy run IDs:', recovered, flush=True)
    # Ask the existing legacy publisher to rebuild current main; no artifact deployment.
    try:
        api('pages/builds', 'POST')
        print('Requested current-main build from the configured legacy publisher', flush=True)
    except subprocess.CalledProcessError as exc:
        print('Build request unavailable; retain existing automatic publisher:', exc.stderr, flush=True)
    build = gate.wait_for_legacy(REPO, TARGET, attempts=180, interval=5)
    print('::notice::Verified successful legacy publication: ' + build['commit'], flush=True)
    os.environ['GITHUB_SHA'] = build['commit']
    # The repository-wide checker executes its checks at module top level.
    load('cbf_original_live_check', 'scripts/check_deployment.py')
    strict = load('cbf_strict_live_check', 'scripts/cbf92764/check_deployment.py')
    strict.main()
    print('::notice::PASS actual HTTPS root, dashboard, six category pages, assets, full inventory, per-row source links, provider replay and unresolved summary', flush=True)
    # Retry only this delivery's failed production publisher gates now that a
    # successful legacy publication exists. Never rerun another workflow/scope.
    for run_id in (39611749011, 39613200669):
        run = api(f'actions/runs/{run_id}')
        if (run.get('conclusion') == 'failure'
                and run.get('name') == 'Verify and publish dashboard'
                and run.get('path') == '.github/workflows/pages.yml'):
            api(f'actions/runs/{run_id}/rerun-failed-jobs', 'POST')
            print(f'::notice::Retried failed production publisher gate {run_id}', flush=True)


if __name__ == '__main__':
    main()
