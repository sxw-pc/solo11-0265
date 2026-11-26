import json
import unittest
from pathlib import Path
from telemetrycourt import spool,store


class FrameTests(unittest.TestCase):
    def test_receiver_frame_changes_outbound_result(self):
        db=store.connect(':memory:'); self.addCleanup(db.close)
        for sub in ('cover','agent'):
            for event in json.loads(Path(f'fixtures/{sub}_normal.json').read_text(encoding='utf8')):
                store.run(db,sub,event)
        pack=json.loads(Path('fixtures/spool_frames.json').read_text(encoding='utf8'))
        sent=spool.run(db,pack)
        self.assertEqual(sent['planned'][0]['encoding'],{'wire':5,'decoded':8,'base':['sample-10',1,3]})
        missed=spool.run(db,{**pack,'acknowledged':[['sample-10',2,3]]})
        self.assertEqual(missed['deferred'],[{'sample':'sample-20','reason':'frame_base_unavailable'}])
