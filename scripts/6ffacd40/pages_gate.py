#!/usr/bin/env python3
"""Select the configured Pages publisher; never double-deploy over a legacy build.

Legacy Pages may retain orphaned 'building' records indefinitely. Only a successful
build containing the validated SHA is evidence of publication. Unrelated old active
records are neither evidence of current activity nor a reason to deploy an older
Actions artifact over newer source commits. Uses the official GitHub API via gh.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import time


def configured_publisher(pages, branch='main'):
    mode = pages.get('build_type')
    if mode == 'workflow':
        return 'actions'
    if mode == 'legacy' and pages.get('source') == {'branch': branch, 'path': '/'}:
        return 'legacy'
    raise ValueError('Unsupported or unverified Pages publisher/source: ' + str(pages))


def published_build(builds, target, contains):
    """Only accept built target/descendant; errored/pending/older/unrelated fail closed."""
    for build in builds:
        commit = build.get('commit')
        if build.get('status') != 'built' or not commit:
            continue
        if commit == target or contains(target, commit):
            return build
    return None


def gh_api(endpoint):
    response = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True, check=True)
    return json.loads(response.stdout)


def wait_for_legacy(repo, target, attempts=36, interval=5, api=gh_api, sleep=time.sleep):
    cache = {}

    def contains(base, head):
        if head not in cache:
            comparison = api(f'repos/{repo}/compare/{base}...{head}')
            cache[head] = comparison.get('status') in ('ahead', 'identical')
        return cache[head]

    for attempt in range(attempts):
        build = published_build(api(f'repos/{repo}/pages/builds?per_page=20'), target, contains)
        if build:
            return build
        if attempt + 1 < attempts:
            sleep(interval)
    raise RuntimeError('No successful legacy Pages build containing validated SHA; refusing to overwrite another publisher')


def main():
    repo, target = os.environ['GH_REPO'], os.environ['GITHUB_SHA']
    pages = gh_api(f'repos/{repo}/pages')
    publisher = configured_publisher(pages)
    if publisher == 'legacy':
        build = wait_for_legacy(repo, target)
        print(f"Legacy Pages published {build['commit']} containing {target}; no second artifact deployment")
    else:
        print('Pages uses Actions; deploying the checked artifact')
    url = pages.get('html_url')
    if not isinstance(url, str) or not url.startswith('https://') or '\n' in url or '\r' in url:
        raise ValueError('Unverified Pages URL')
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        output.write(f'publisher={publisher}\npage_url={url}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
