import json
from pathlib import Path
import unittest

from telemetrycourt import autoscale, loadlab


class OfflineLoadLabTests(unittest.TestCase):
    def setUp(self):
        fixture = Path(__file__).parents[1] / 'fixtures' / 'load_lab_normal.json'
        self.fixture = json.loads(fixture.read_text(encoding='utf-8-sig'))

    def test_queue_keeps_wait_and_identity_through_backlog(self):
        output = loadlab.run(self.fixture)
        self.assertEqual([x['backlog'] for x in output['samples']], [0, 3, 2, 1])
        completed = [item for row in output['samples'] for item in row['completed']]
        self.assertEqual([(x['request'], x['wait']) for x in completed], [(0, 0), (1, 1), (2, 2)])
        self.assertEqual(output['unfinished'], 1)

    def test_controller_uses_observed_backlog_and_preserves_work(self):
        result = autoscale.run(self.fixture)
        self.assertEqual([x['replicas'] for x in result['samples']], [1, 1, 2, 3])
        self.assertEqual([x['next_replicas'] for x in result['samples']], [1, 2, 3, 2])
        self.assertEqual(result['unfinished'], 0)
        self.assertEqual(sum(len(x['completed']) for x in result['samples']), 4)
        without_burst = autoscale.run({**self.fixture, 'arrivals': [0, 0, 0, 0]})
        self.assertEqual([x['next_replicas'] for x in without_burst['samples']], [1, 1, 1, 1])

    def test_bad_numeric_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            loadlab.run({**self.fixture, 'service_per_replica': True})
        with self.assertRaises(ValueError):
            autoscale.run({**self.fixture, 'max_replicas': 0})
