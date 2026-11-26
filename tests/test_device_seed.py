import tempfile
import unittest
from pathlib import Path

from telemetrycourt import device, store


class PersistedDeviceTest(unittest.TestCase):
    def test_selected_detail_is_really_openable_after_reconnect(self):
        name = 'diagnostics-a'
        spec = dict(device=name, revision='v1', threshold=2)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'device.sqlite'
            db = store.connect(path)
            device.run(db, dict(op='configure', **spec))
            for tick in [0, 3]:
                device.run(db, dict(op='receive', device=name, sample=dict(tick=tick, high=True)))
            self.assertFalse(device.run(db, dict(op='checkpoint', device=name))['state']['fired'])
            device.run(db, dict(op='enable', device=name, space=10))
            sample = dict(tick=4, high=True, detail='four')
            result = device.run(db, dict(op='receive', device=name, sample=sample))
            self.assertEqual(result, dict(decision='captured', handle='0/v1'))
            db.close()
            db = store.connect(path)
            opened = device.run(db, dict(op='open', device=name, handle=result['handle']))
            self.assertEqual(opened, dict(sample=sample, episode=0, revision='v1'))
            self.assertEqual(device.run(db, dict(op='ack', device=name, handle=result['handle'],
                                                 revision='v0', sample=sample)), {'decision': 'stale_revision'})
            db.close()
