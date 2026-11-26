import json
import unittest
from pathlib import Path

from telemetrycourt import sourcejump


class ProfileNavTest(unittest.TestCase):
    def test_same_address_crosses_real_load_boundary(self):
        fixture = json.loads((Path(__file__).resolve().parents[1] / 'fixtures/profile_nav_normal.json').read_text())
        old, new, plugin = sourcejump.run(fixture)
        self.assertEqual(old['stack'][0]['text'], 'read_cached(old_slot)')
        self.assertEqual(new['stack'][0]['text'], 'read_cached(new_slot)')
        self.assertEqual(plugin['build'], 'plug-K')
        self.assertEqual(sourcejump.historical(fixture, 10, 200)['decision'], 'unmapped_address')
        self.assertEqual(sourcejump.repair(fixture, new['stack'][0]['origin'])['text'], 'read_repairable_slot()')
