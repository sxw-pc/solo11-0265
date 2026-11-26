import json
import unittest
from pathlib import Path
from telemetrycourt import histogram,store


class HistogramTests(unittest.TestCase):
    def test_histogram_respects_archive_membership_and_boundary_edges(self):
        db=store.connect(':memory:'); self.addCleanup(db.close)
        for sub in ('cover','agent'):
            for e in json.loads(Path(f'fixtures/{sub}_normal.json').read_text(encoding='utf8')):
                store.run(db,sub,e)
        fixture=json.loads(Path('fixtures/histogram_normal.json').read_text(encoding='utf8'))
        report=histogram.run(db,fixture)
        self.assertEqual([b['counts'] for b in report['buckets']], [[1,0,0],[0,0,1]])
        other=histogram.run(db,{**fixture,'values':{'sample-20':30}})
        self.assertEqual(other['buckets'][0]['missing'],['sample-10'])
        self.assertEqual(other['buckets'][1]['counts'],[0,1,0])
