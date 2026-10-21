"""Safety gates for the branch-only Pages publication diagnostic."""
import importlib.util
from pathlib import Path
import unittest
from datetime import datetime, timezone

SPEC = importlib.util.spec_from_file_location('cbf_publication_recovery', Path(__file__).resolve().parents[1] / 'scripts/cbf92764/verify_publication.py')
RECOVERY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RECOVERY)


class PublicationRecoverySafety(unittest.TestCase):
    def setUp(self):
        self.run = {'name': 'pages build and deployment', 'event': 'dynamic', 'status': 'in_progress', 'created_at': '2026-10-21T13:00:00Z'}
        self.now = datetime(2026, 10, 21, 14, tzinfo=timezone.utc)

    def test_only_old_run_with_all_terminal_jobs(self):
        self.assertTrue(RECOVERY.terminal_legacy(self.run, [{'status': 'completed'}], self.now))

    def test_never_cancel_active_or_queued_job(self):
        for status in ('in_progress', 'queued', 'pending'):
            self.assertFalse(RECOVERY.terminal_legacy(self.run, [{'status': 'completed'}, {'status': status}], self.now))

    def test_never_cancel_refresh_or_other_workflow(self):
        for field, value in [('name', 'Verified CS2 dashboard'), ('event', 'workflow_dispatch'), ('status', 'completed')]:
            self.assertFalse(RECOVERY.terminal_legacy(dict(self.run, **{field: value}), [{'status': 'completed'}], self.now))

    def test_never_cancel_run_without_jobs(self):
        self.assertFalse(RECOVERY.terminal_legacy(self.run, [], self.now))

    def test_never_cancel_recent_terminal_run(self):
        self.assertFalse(RECOVERY.terminal_legacy(dict(self.run, created_at='2026-10-21T13:59:00Z'), [{'status': 'completed'}], self.now))
