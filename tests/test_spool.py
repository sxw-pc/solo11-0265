import json
import unittest
from pathlib import Path

from telemetrycourt import spool, store


class SpoolTests(unittest.TestCase):
    def setUp(self):
        self.db = store.connect(':memory:')
        self.addCleanup(self.db.close)
        for sub in ('cover','agent'):
            for event in json.loads(Path(f'fixtures/{sub}_normal.json').read_text(encoding='utf-8')):
                store.run(self.db,sub,event)
        self.fixture = json.loads(Path('fixtures/spool_normal.json').read_text(encoding='utf-8'))

    def test_spool_skips_packets_that_exceed_budget(self):
        result = spool.run(self.db,self.fixture)
        self.assertEqual([p['id'] for p in result['planned']], ['sample-10','sample-30'])
        self.assertEqual(result['deferred'], [{'sample':'sample-20','reason':'budget_exhausted'}])
        self.assertEqual(result['remaining_bytes'],0)

    def test_drift_invalidates_all_export_candidates_from_lease(self):
        drift = {'event_id':'new-drift','id':'new-drift','op':'drift','lease':'lease-a','offset':20,'max_abs':5,'generation':1,'at':40}
        self.assertEqual(store.run(self.db,'agent',drift)['decision'],'drift_isolated')
        result=spool.run(self.db,self.fixture)
        self.assertFalse(result['planned'])
        self.assertEqual({p['reason'] for p in result['deferred']},{'sample_unavailable'})
