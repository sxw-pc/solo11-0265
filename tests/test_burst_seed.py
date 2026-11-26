import json
import unittest
from pathlib import Path
from telemetrycourt import burst, capture


class BurstTest(unittest.TestCase):
    def test_threshold_changes_real_captured_sample(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/burst_normal.json').read_text())
        early = burst.run(fixture)['state']
        late = burst.run({**fixture, 'threshold': 3})['state']
        self.assertEqual({key: value['tick'] for key, value in early['captures'].items()}, {'0': 1, '4': 5})
        self.assertEqual({key: value['tick'] for key, value in late['captures'].items()}, {'0': 2})
        self.assertEqual((early['remaining'], late['remaining']), (0, 1))

    def test_repeat_and_conflicting_ticket_do_not_spend(self):
        state = dict(remaining=2, captures={})
        self.assertEqual(capture.take(state, '5', dict(tick=5)), 'captured')
        self.assertEqual(capture.take(state, '5', dict(tick=5)), 'already_captured')
        self.assertEqual(capture.take(state, '5', dict(tick=6)), 'ticket_conflict')
        self.assertEqual(state['remaining'], 1)

    def test_streak_saturates_and_pending_credit_stays_live(self):
        fixture = dict(credit=0, threshold=2, samples=[dict(tick=tick, high=True) for tick in (10, 20, 40)])
        result = burst.run(fixture)
        self.assertEqual(result['outcomes'], ['waiting', 'out_of_credit', 'out_of_credit'])
        self.assertEqual(result['state']['streak'], 2)
        self.assertFalse(result['state']['fired'])
        self.assertEqual(result['state']['opened_at'], 10)
