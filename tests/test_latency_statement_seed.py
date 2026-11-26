import json
import unittest
from pathlib import Path

from telemetrycourt import latency_statement, stage_times, store


class LatencyStatementTest(unittest.TestCase):
    def test_pairing_changes_statement_but_not_marginals(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/latency_statement_normal.json').read_text())
        alternative = [{'request': 'p', 'duration': 0}, {'request': 'q', 'duration': 4},
                       {'request': 'r', 'duration': 4}]
        self.assertEqual(stage_times.marginal(fixture['back']), stage_times.marginal(alternative))
        db = store.connect(':memory:')
        try:
            self.assertEqual(latency_statement.run(db, fixture), {'late': 1, 'status': 'within_contract'})
            revised = dict(fixture, statement='other', back=alternative)
            self.assertEqual(latency_statement.run(db, revised), {'late': 2, 'status': 'outside_contract'})
            self.assertEqual(latency_statement.published(db, fixture['statement'])['late'], 1)
        finally:
            db.close()
