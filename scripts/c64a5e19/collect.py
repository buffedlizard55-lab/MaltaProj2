#!/usr/bin/env python3
"""Collect the every-match snapshot using the shared, evidence-retaining collector.

Only the output directory changes. This removes divergent market parsers and preserves
original observation times/cache ages on repeated failures. No authenticated APIs or
access-control bypasses. Run on GitHub Actions, where source access is available.
"""
import base64
import json
import importlib.util
from pathlib import Path
from verified_engine import load_engine


def main():
    collector = load_engine('collect.py')
    collector.OUT = Path(__file__).resolve().parents[2] / 'data/c64a5e19'
    evidence_path = collector.OUT / 'official_inputs.json'
    try:
        evidence = json.loads(evidence_path.read_text())
    except (OSError, ValueError):
        evidence = {}
    original_fetch = collector.fetch
    # Session 69e4c06a: a cached lobby omitted newly listed fixtures. Retain cache
    # metadata; requesting revalidation is not itself a fresh-evidence assertion.
    support_path = Path(__file__).resolve().parents[1] / '69e4c06a/refresh.py'
    spec = importlib.util.spec_from_file_location('canonical_lobby_refresh', support_path)
    support = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(support)

    def retain_inputs(url, *args, **kwargs):
        body, meta = support.fetch_recent_lobby(original_fetch, url, *args, **kwargs)
        if meta.get('status') == 200 and body:
            if url == collector.LOBBY_PAGE:
                state = collector.core.lobby_state(body.decode('utf-8', 'replace'))
                if state.get('fixtures'):
                    evidence['lobby'] = {'url': url, 'metadata': meta, 'transfer_state': state}
            elif '/contents/live/' in url and '/standings_global_' in url:
                blob = json.loads(body)
                if blob.get('content'):
                    evidence['valve'] = {'url': url, 'metadata': meta, 'git_blob_sha': blob.get('sha'),
                                         'markdown': base64.b64decode(blob['content']).decode('utf-8')}
        return body, meta

    collector.fetch = retain_inputs
    result = collector.main()
    evidence_path.write_text(json.dumps(evidence, indent=1, ensure_ascii=False) + '\n')
    # A separate, replayable extension reads explicit contract rules, never tickers
    # or settlement clocks. The builder admits it only for existing market gaps.
    spec = importlib.util.spec_from_file_location('canonical_rule_kickoffs',
        Path(__file__).resolve().parents[1] / '69e4c06a/kalshi.py')
    rules = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rules)
    rules.normalize_saved_capture(collector.OUT)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
