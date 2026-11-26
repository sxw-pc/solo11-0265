import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from telemetrycourt import meters, pull, store


class OfflineMeterPullTests(unittest.TestCase):
    def test_source_balance_changes_the_real_receipt(self):
        db = store.connect(':memory:')
        self.addCleanup(db.close)
        path = Path(__file__).parents[1] / 'fixtures' / 'meter_pull_normal.json'
        output = pull.run(db, json.loads(path.read_text(encoding='utf-8')))
        self.assertEqual([entry.get('amount') for entry in output], [None, 7, None, 7, 3])
        self.assertEqual(meters.balance(db, 'requests'), 0)

    def test_lost_reply_replay_survives_reopening(self):
        credit = {'id':'c', 'op':'credit', 'meter':'calls', 'amount':5}
        take = {'id':'p', 'op':'pull', 'meter':'calls'}
        with TemporaryDirectory() as located:
            path = Path(located) / 'copy.sqlite'
            db = store.connect(path)
            first = pull.run(db, [credit, take])[1]
            db.close()
            db = store.connect(path)
            again = pull.run(db, [take, {**take, 'meter':'different'}])
            self.assertEqual(again, [first, {'decision':'pull_identity_conflict'}])
            self.assertEqual(meters.balance(db,'calls'),0)
            db.close()
