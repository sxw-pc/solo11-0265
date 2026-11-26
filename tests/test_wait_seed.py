import json
import unittest
from pathlib import Path

from telemetrycourt import waitresult


class WaitTest(unittest.TestCase):
    def test_observed_contention_changes_target_completion(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/wait_normal.json').read_text())
        fixed = waitresult.run(fixture)
        self.assertEqual((fixed['completion'], fixed['decision']), (7, 'late'))
        self.assertEqual(fixed['timeline']['left']['start'], 4)
        fixture['tasks'][0]['worker'] = 'W'
        isolated = waitresult.run(fixture)
        self.assertEqual((isolated['completion'], isolated['decision']), (5, 'on_time'))
