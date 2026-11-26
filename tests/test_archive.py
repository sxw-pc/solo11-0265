import json
import unittest
from pathlib import Path
from telemetrycourt import archive, store


class ArchiveTests(unittest.TestCase):
    def test_half_open_rollup_and_drift_exclusion(self):
        db=store.connect(':memory:')
        self.addCleanup(db.close)
        for sub in ('cover','agent'):
            for event in json.loads(Path(f'fixtures/{sub}_normal.json').read_text(encoding='utf-8')):
                store.run(db,sub,event)
        fixture=json.loads(Path('fixtures/archive_normal.json').read_text(encoding='utf-8'))
        rollup=archive.run(db,fixture)
        self.assertEqual([row['sample_ids'] for row in rollup['buckets']],[['sample-10'],['sample-20']])
        out=store.run(db,'agent',{'event_id':'drift-new','op':'drift','id':'drift-new','lease':'lease-a','offset':6,'max_abs':2,'generation':1,'at':40})
        self.assertEqual(out['decision'],'drift_isolated')
        self.assertEqual(archive.run(db,fixture)['buckets'],[])
