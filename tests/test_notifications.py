import json
import unittest
from pathlib import Path
from telemetrycourt import notifications, store


class NotificationTests(unittest.TestCase):
    def test_active_labels_and_route_budget(self):
        db=store.connect(':memory:')
        self.addCleanup(db.close)
        for sub in ('cover','agent','blind'):
            for command in json.loads(Path(f'fixtures/{sub}_normal.json').read_text(encoding='utf-8')):
                store.run(db,sub,command)
        store.run(db,'blind',{'event_id':'label-2','op':'label','id':'label-2','case':'case-2','alert':'alert-2','at':71})
        fixture=json.loads(Path('fixtures/notifications_normal.json').read_text(encoding='utf-8'))
        first=notifications.run(db,fixture)
        self.assertEqual([x['alert'] for x in first['pages']],['alert-1'])
        self.assertEqual(first['skipped'],[{'alert':'alert-2','reason':'no_active_blind_alert'}])
        second=notifications.run(db,{**fixture,'alerts':[fixture['alerts'][0]]*2})
        self.assertEqual(second['skipped'],[{'alert':'alert-1','reason':'route_exhausted'}])
