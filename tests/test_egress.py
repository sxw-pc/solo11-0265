import json
import unittest
from pathlib import Path
from telemetrycourt import egress,store


class EgressTests(unittest.TestCase):
    def test_credit_is_rolling_and_bound_to_delivery(self):
        db=store.connect(':memory:'); self.addCleanup(db.close)
        for sub in ('cover','agent'):
            for e in json.loads(Path(f'fixtures/{sub}_normal.json').read_text(encoding='utf8')):
                store.run(db,sub,e)
        fixture=json.loads(Path('fixtures/egress_normal.json').read_text(encoding='utf8'))
        self.assertEqual(egress.run(db,fixture)['used'],12)
        self.assertEqual(egress.run(db,fixture)['decision'],'already_reserved')
        self.assertEqual(egress.run(db,{**fixture,'delivery':'id-2','at':49})['used'],0)
        self.assertEqual(egress.run(db,{**fixture,'delivery':'id-3','at':50})['used'],12)
