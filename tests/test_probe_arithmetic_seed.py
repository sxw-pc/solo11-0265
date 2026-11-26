import json
import unittest
from pathlib import Path

from telemetrycourt import probe_review


class ProbeArithmeticTest(unittest.TestCase):
    def test_only_changing_instruction_order_changes_actual_review(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/probe_arithmetic_normal.json').read_text())
        original = probe_review.run(fixture)
        self.assertEqual((original['value'], original['decision']), (3, 'normal'))
        self.assertTrue(original['trace'][0]['clipped'])
        first, second, add, third, subtract = fixture['program']
        revised = probe_review.run({**fixture, 'program': [first, second, third, subtract, add]})
        self.assertEqual((revised['value'], revised['decision']), (7, 'open_review'))
        self.assertTrue(all(not row['clipped'] for row in revised['trace']))
