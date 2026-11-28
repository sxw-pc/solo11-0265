import json
import tempfile
import unittest
from pathlib import Path

from telemetrycourt import burst, device, store

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/device_normal.json'
NAME = 'live-device'
FOUR = dict(tick=4, high=True, detail='four')
FIVE = dict(tick=5, high=True, detail='five')
SIX = dict(tick=6, high=False, detail='six')


def run_actions(path, actions):
    db = store.connect(path)
    try:
        return [device.run(db, action) for action in actions]
    finally:
        db.close()


def rehearsed(path):
    """Open a segment rehearsed under the old rule with detail writing off."""
    db = store.connect(path)
    device.run(db, dict(op='configure', device=NAME, revision='v1', threshold=2))
    device.run(db, dict(op='receive', device=NAME, sample=dict(tick=0, high=True, detail='zero')))
    device.run(db, dict(op='receive', device=NAME, sample=dict(tick=3, high=True, detail='three')))
    return db


class FixtureReferenceTest(unittest.TestCase):
    def test_initial_threshold_selects_the_real_detail(self):
        actions = json.loads(FIXTURE.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as temp:
            results = run_actions(Path(temp) / 'plain.sqlite', actions)
        self.assertEqual(results[-2], {'decision': 'captured', 'handle': '0/v1'})
        self.assertEqual(results[-1], dict(episode=0, revision='v1',
                                           sample=dict(tick=4, high=True, detail='c')))
        extra = dict(op='receive', device='demo-device',
                     sample=dict(tick=5, high=True, detail='five'))
        extended = actions[:-1] + [extra] + actions[-1:]
        captures, opened = {}, {}
        for threshold in (2, 4):
            tuned = [dict(extended[0], threshold=threshold)] + extended[1:]
            with tempfile.TemporaryDirectory() as temp:
                results = run_actions(Path(temp) / f't{threshold}.sqlite', tuned)
            captures[threshold] = (results[-3], results[-2])
            opened[threshold] = results[-1]
        self.assertEqual(captures[2], ({'decision': 'captured', 'handle': '0/v1'},
                                       {'decision': 'waiting'}))
        self.assertEqual(captures[4], ({'decision': 'waiting'},
                                       {'decision': 'captured', 'handle': '0/v1'}))
        self.assertEqual(opened[2], dict(episode=0, revision='v1',
                                         sample=dict(tick=4, high=True, detail='c')))
        self.assertEqual(opened[4], dict(episode=0, revision='v1',
                                         sample=dict(tick=5, high=True, detail='five')))


class LiveHandoverTest(unittest.TestCase):
    def test_skipped_ticks_collapse_to_one_rehearsal_point(self):
        sparse = [dict(tick=tick, high=True) for tick in (0, 3)]
        dense = [dict(tick=tick, high=True) for tick in (0, 1, 2, 3)]
        points = []
        for samples in (sparse, dense):
            state = burst.run(dict(credit=0, threshold=2, samples=samples))['state']
            points.append((state['opened_at'], state['streak'], state['fired'], state['captures']))
        self.assertEqual(points, [(0, 2, False, {}), (0, 2, False, {})])

    def test_rehearsal_point_is_independently_readable(self):
        with tempfile.TemporaryDirectory() as temp:
            db = rehearsed(Path(temp) / 'dev.sqlite')
            point = device.run(db, dict(op='checkpoint', device=NAME))
            self.assertEqual((point['revision'], point['threshold'], point['last_tick']), ('v1', 2, 3))
            self.assertEqual(point['state']['opened_at'], 0)
            self.assertEqual(point['state']['streak'], 2)
            self.assertEqual(point['state']['captures'], {})
            self.assertEqual(point['state']['remaining'], 0)
            self.assertEqual(point['state']['last_sample'], dict(tick=3, high=True, detail='three'))
            self.assertIsNone(device.run(db, dict(op='open', device=NAME, handle='0/v1')))
            db.close()

    def test_ambiguous_handover_returns_replayable_witnesses(self):
        with tempfile.TemporaryDirectory() as temp:
            db = rehearsed(Path(temp) / 'dev.sqlite')
            result = device.run(db, dict(op='revise', device=NAME, revision='v2', threshold=4))
            self.assertEqual(result['decision'], 'ambiguous')
            self.assertEqual(result['probe'], dict(tick=4, high=True))
            witnesses = result['witnesses']
            self.assertEqual([witness['count'] for witness in witnesses], [2, 4])
            outcomes = []
            for witness in witnesses:
                replayed = burst.run(dict(credit=0, threshold=2, samples=witness['samples']))['state']
                self.assertEqual((replayed['opened_at'], replayed['streak'], replayed['fired']),
                                 (0, 2, False))
                live = burst.run(dict(credit=0, threshold=4, samples=witness['samples']))['state']
                live['remaining'] = 1
                outcomes.append(burst.advance(live, dict(result['probe']), 4))
            self.assertEqual(outcomes, ['waiting', 'captured'])
            self.assertEqual([witness['probe_outcome'] for witness in witnesses], outcomes)
            point = device.run(db, dict(op='checkpoint', device=NAME))
            self.assertEqual((point['revision'], point['threshold']), ('v1', 2))
            db.close()

    def test_sparse_catalog_reconstructs_live_state_for_new_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'dev.sqlite'
            db = rehearsed(path)
            catalog = [dict(tick=0, high=True, detail='zero'), dict(tick=3, high=True, detail='three')]
            result = device.run(db, dict(op='revise', device=NAME, revision='v2', threshold=4,
                                         catalog=catalog))
            self.assertEqual(result['decision'], 'switched')
            self.assertEqual(result['segment'], dict(opened_at=0, count=2, streak=2))
            db.close()
            db = store.connect(path)
            device.run(db, dict(op='enable', device=NAME, space=10))
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=FOUR)),
                             {'decision': 'waiting'})
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=FIVE)),
                             {'decision': 'captured', 'handle': '0/v2'})
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=SIX)),
                             {'decision': 'episode_closed'})
            self.assertEqual(device.run(db, dict(op='open', device=NAME, handle='0/v2')),
                             dict(episode=0, revision='v2', sample=FIVE))
            self.assertEqual(device.run(db, dict(op='ack', device=NAME, handle='0/v2',
                                                 revision='v1', sample=FIVE)),
                             {'decision': 'stale_revision'})
            self.assertEqual(device.run(db, dict(op='ack', device=NAME, handle='0/v2',
                                                 revision='v2', sample=FIVE)),
                             {'decision': 'existing_detail'})
            db.close()

    def test_dense_catalog_attributes_t4_to_the_new_rule(self):
        with tempfile.TemporaryDirectory() as temp:
            db = rehearsed(Path(temp) / 'dev.sqlite')
            catalog = [dict(tick=tick, high=True) for tick in (0, 1, 2, 3)]
            result = device.run(db, dict(op='revise', device=NAME, revision='v2', threshold=4,
                                         catalog=catalog))
            self.assertEqual(result['decision'], 'switched')
            self.assertEqual(result['segment'], dict(opened_at=0, count=4, streak=4))
            device.run(db, dict(op='enable', device=NAME, space=10))
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=FOUR)),
                             {'decision': 'captured', 'handle': '0/v2'})
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=FIVE)),
                             {'decision': 'waiting'})
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=SIX)),
                             {'decision': 'episode_closed'})
            self.assertEqual(device.run(db, dict(op='open', device=NAME, handle='0/v2')),
                             dict(episode=0, revision='v2', sample=FOUR))
            db.close()

    def test_last_record_only_catalog_loses_the_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            db = rehearsed(Path(temp) / 'dev.sqlite')
            result = device.run(db, dict(op='revise', device=NAME, revision='v2', threshold=4,
                                         catalog=[dict(tick=3, high=True, detail='three')]))
            self.assertEqual(result['decision'], 'ambiguous')
            self.assertEqual(result['probe'], dict(tick=4, high=True))
            self.assertEqual([witness['count'] for witness in result['witnesses']], [2, 4])
            point = device.run(db, dict(op='checkpoint', device=NAME))
            self.assertEqual((point['revision'], point['threshold']), ('v1', 2))
            db.close()

    def test_truncated_count_alone_does_not_block_an_equivalent_switch(self):
        with tempfile.TemporaryDirectory() as temp:
            db = rehearsed(Path(temp) / 'dev.sqlite')
            result = device.run(db, dict(op='revise', device=NAME, revision='v2', threshold=2))
            self.assertEqual(result['decision'], 'switched')
            self.assertEqual(result['segment'], dict(opened_at=0, count=None, streak=2))
            device.run(db, dict(op='enable', device=NAME, space=10))
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=FOUR)),
                             {'decision': 'captured', 'handle': '0/v2'})
            self.assertEqual(device.run(db, dict(op='open', device=NAME, handle='0/v2')),
                             dict(episode=0, revision='v2', sample=FOUR))
            db.close()

    def test_field_diagnosis_defers_new_rule_until_segment_closes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'dev.sqlite'
            db = rehearsed(path)
            result = device.run(db, dict(op='revise', device=NAME, revision='v2', threshold=4,
                                         defer=True))
            self.assertEqual(result, {'decision': 'deferred', 'revision': 'v1', 'threshold': 2,
                                      'pending': {'revision': 'v2', 'threshold': 4}})
            db.close()
            db = store.connect(path)
            point = device.run(db, dict(op='checkpoint', device=NAME))
            self.assertEqual(point['pending'], {'revision': 'v2', 'threshold': 4})
            device.run(db, dict(op='enable', device=NAME, space=10))
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=FOUR)),
                             {'decision': 'captured', 'handle': '0/v1'})
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=FIVE)),
                             {'decision': 'waiting'})
            self.assertEqual(device.run(db, dict(op='receive', device=NAME, sample=SIX)),
                             {'decision': 'episode_closed',
                              'activated': {'revision': 'v2', 'threshold': 4}})
            db.close()
            db = store.connect(path)
            point = device.run(db, dict(op='checkpoint', device=NAME))
            self.assertEqual((point['revision'], point['threshold'], point['pending']),
                             ('v2', 4, None))
            self.assertEqual(device.run(db, dict(op='open', device=NAME, handle='0/v1')),
                             dict(episode=0, revision='v1', sample=FOUR))
            for tick, detail in ((7, 'seven'), (8, 'eight'), (9, 'nine')):
                self.assertEqual(device.run(db, dict(op='receive', device=NAME,
                                                     sample=dict(tick=tick, high=True,
                                                                 detail=detail))),
                                 {'decision': 'waiting'})
            self.assertEqual(device.run(db, dict(op='receive', device=NAME,
                                                 sample=dict(tick=10, high=True, detail='ten'))),
                             {'decision': 'captured', 'handle': '7/v2'})
            self.assertEqual(device.run(db, dict(op='open', device=NAME, handle='7/v2')),
                             dict(episode=7, revision='v2',
                                  sample=dict(tick=10, high=True, detail='ten')))
            self.assertEqual(device.run(db, dict(op='ack', device=NAME, handle='0/v1',
                                                 revision='v1', sample=FOUR)),
                             {'decision': 'stale_revision'})
            self.assertEqual(device.run(db, dict(op='ack', device=NAME, handle='0/v1',
                                                 revision='v2', sample=FOUR)),
                             {'decision': 'unknown_detail'})
            self.assertEqual(device.run(db, dict(op='ack', device=NAME, handle='7/v2',
                                                 revision='v2',
                                                 sample=dict(tick=10, high=True, detail='ten'))),
                             {'decision': 'existing_detail'})
            db.close()


if __name__ == '__main__':
    unittest.main()
