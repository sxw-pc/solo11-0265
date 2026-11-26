import json
import unittest
from pathlib import Path

from telemetrycourt import emitlog, logactions, store


class LogActionTest(unittest.TestCase):
    def test_compact_rows_lose_discriminating_data(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/log_actions_normal.json').read_text())
        with store.connect(':memory:') as db:
            self.assertEqual(logactions.run(db, fixture), ['sample-again', 'check-restart'])
            self.assertEqual(logactions.active(db, 'local-a'), {1: 'sample-again', 2: 'check-restart'})
        rich = fixture['rows'][1]
        self.assertEqual(emitlog.compact(rich), emitlog.compact({**rich, 'phase': 'first'}))
        with store.connect(':memory:') as db:
            compact = emitlog.compact(rich)
            self.assertEqual(logactions.run(db, {**fixture, 'rows': [compact]}), ['none'])
            self.assertEqual(logactions.active(db, 'local-a'), {})
