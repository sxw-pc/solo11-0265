import copy
import json
import unittest
from pathlib import Path

from telemetrycourt import sourcejump

FIXTURE = Path(__file__).resolve().parents[1] / 'fixtures/profile_nav_batch.json'


def load_fixture():
    # Fixture JSON is untrusted data: the test runner uses -I and only this
    # synthetic load table and its archived source text are ever interpreted.
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


class BatchClockTest(unittest.TestCase):
    """One recovery, two clock explanations (+0/+2), shared by every frame."""

    def setUp(self):
        self.fixture = load_fixture()
        self.batch = self.fixture['batches'][0]

    def test_load_facts_select_single_offset_for_whole_batch(self):
        result = sourcejump.navigate_batch(self.fixture, self.batch)
        # +0 is falsified by the real load log: address 200 (plug-K) is only
        # loaded at host time 12, so the whole batch keeps the single +2 clock.
        self.assertEqual(result['decision'], 'batch_navigated')
        self.assertEqual(result['offsets'], [2])
        first, second = result['frames']
        self.assertEqual(first['build'], 'app-B')
        self.assertEqual(first['stack'][0]['text'], 'read_cached(new_slot)')
        self.assertEqual(second['build'], 'plug-K')
        self.assertEqual(second['stack'][0]['text'], 'poll_clock()')

    def test_zero_offset_is_rejected_with_real_load_evidence(self):
        result = sourcejump.navigate_batch(self.fixture, self.batch)
        rejected = result.get('rejected')
        self.assertIsNone(rejected)  # one explanation survived, no batch reject
        # Re-run on mutually exclusive load regions: address 100 is only
        # covered at host time 10 and address 200 only at host time 12, so no
        # single offset explains the whole batch.
        exclusive = load_fixture()
        exclusive['images'] = [
            {'begin': 0, 'end': 12, 'base': 100, 'size': 8, 'build': 'app-A'},
            {'begin': 12, 'end': 30, 'base': 200, 'size': 8, 'build': 'plug-K'},
        ]
        refused = sourcejump.navigate_batch(exclusive, exclusive['batches'][0])
        self.assertEqual(refused['decision'], 'batch_clock_rejected')
        reasons = {item['offset']: (item['frame'], item['reason'])
                   for item in refused['rejected']}
        self.assertEqual(reasons,
                         {0: (200, 'unmapped_address'),
                          2: (100, 'unmapped_address')})
        self.assertNotIn('frames', refused)

    def test_missing_debug_symbol_does_not_falsify_loading_build(self):
        # Remove only plug-K symbols; its load fact still pins the batch to +2.
        self.fixture['symbols'].pop('plug-K')
        result = sourcejump.navigate_batch(self.fixture, self.batch)
        self.assertEqual(result['decision'], 'batch_navigated')
        self.assertEqual(result['offsets'], [2])
        first, second = result['frames']
        self.assertEqual(first['build'], 'app-B')
        self.assertEqual(first['decision'], 'historical_source')
        self.assertEqual(second['build'], 'plug-K')
        self.assertEqual(second['decision'], 'unmapped_symbol')

    def test_removing_second_frame_leaves_history_ambiguous_between_a_and_b(self):
        batch = {'id': 'ambiguous-one', 'at': 10, 'frames': [100]}
        result = sourcejump.navigate_batch(self.fixture, batch)
        self.assertEqual(result['decision'], 'batch_navigated')
        self.assertEqual(result['offsets'], [0, 2])
        frame = result['frames'][0]
        self.assertEqual(frame['decision'], 'ambiguous')
        builds = {item['build'] for item in frame['interpretations']}
        self.assertEqual(builds, {'app-A', 'app-B'})
        texts = {site['text']
                 for item in frame['interpretations'] for site in item['stack']}
        self.assertEqual(texts, {'read_cached(old_slot)', 'read_cached(new_slot)'})

    def test_ambiguous_frame_keeps_each_explanation_clock_explicit(self):
        batch = {'id': 'ambiguous-one', 'at': 10, 'frames': [100]}
        result = sourcejump.navigate_batch(self.fixture, batch)
        interpretation = result['frames'][0]['interpretations'][0]
        self.assertIn('build', interpretation)
        self.assertIn('offset', interpretation)


class ArchiveNavigationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture()

    def test_archive_opens_historical_b_from_build_symbol_stack(self):
        result = sourcejump.navigate_batch(self.fixture,
                                           self.fixture['batches'][0])
        first = result['frames'][0]
        site = first['stack'][0]
        self.assertEqual(first['build'], 'app-B')
        self.assertEqual(site['origin'], 'B-reader')
        self.assertEqual(site['document'], 'archive-B')
        self.assertEqual(site['line'], 2)
        # The clickable content is the archived original, not current text.
        self.assertEqual(site['text'], 'read_cached(new_slot)')

    def test_missing_symbol_and_cross_build_uncertainty_are_distinct(self):
        ambiguous = sourcejump.navigate_batch(
            self.fixture, {'id': 'a', 'at': 10, 'frames': [100]})
        self.assertEqual(ambiguous['frames'][0]['decision'], 'ambiguous')
        self.fixture['symbols'].pop('plug-K')
        missing = sourcejump.navigate_batch(self.fixture,
                                            self.fixture['batches'][0])
        self.assertEqual(missing['frames'][1]['decision'], 'unmapped_symbol')

    def test_current_workspace_lookalike_is_not_used_as_original(self):
        # Deleting the archived document makes the original unopenable instead
        # of silently falling back to a same-named function in current sources.
        self.fixture['documents'].pop('archive-B')
        result = sourcejump.navigate_batch(self.fixture,
                                           self.fixture['batches'][0])
        self.assertEqual(result['frames'][0]['decision'], 'source_unavailable')


class RepairNavigationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture()

    def _frame(self, batch):
        result = sourcejump.navigate_batch(self.fixture, batch)
        return result['frames'][0]

    def test_converging_lineages_issue_clickable_cursor_with_real_content(self):
        result = sourcejump.navigate_batch(
            self.fixture, {'id': 'b', 'at': 10, 'frames': [100, 200]})
        first, second = result['frames']
        cursor = sourcejump.navigate_repair(self.fixture, second)
        self.assertEqual(cursor['decision'], 'repair_cursor')
        self.assertEqual(cursor['cursor'],
                         {'document': 'fix', 'line': 2,
                          'text': 'read_repairable_slot()'})
        self.assertEqual({trace['origin'] for trace in cursor['provenance']},
                         {'K-loop'})
        b_cursor = sourcejump.navigate_repair(self.fixture, first)
        self.assertEqual(b_cursor['decision'], 'repair_cursor')
        origins = {trace['origin'] for trace in b_cursor['provenance']}
        self.assertEqual(origins, {'B-reader'})
        for trace in b_cursor['provenance']:
            versions = [hop['version'] for hop in trace['history']]
            self.assertEqual(versions, ['migrate-1', 'fix'])
            self.assertTrue(all('text' in hop for hop in trace['history']))

    def test_repair_cursor_survives_ambiguous_history_when_chains_converge(self):
        frame = self._frame({'id': 'a', 'at': 10, 'frames': [100]})
        self.assertEqual(frame['decision'], 'ambiguous')
        cursor = sourcejump.navigate_repair(self.fixture, frame)
        self.assertEqual(cursor['decision'], 'repair_cursor')
        self.assertEqual(cursor['cursor']['text'], 'read_repairable_slot()')
        self.assertEqual({t['origin'] for t in cursor['provenance']},
                         {'A-reader', 'B-reader'})

    def test_redirecting_one_origin_elsewhere_holds_cursor_for_review(self):
        self.fixture['lineages']['B-reader'] = [
            {'version': 'fix', 'document': 'fix', 'line': 1}]
        frame = self._frame({'id': 'a', 'at': 10, 'frames': [100]})
        cursor = sourcejump.navigate_repair(self.fixture, frame)
        self.assertEqual(cursor['decision'], 'repair_split')
        self.assertEqual(cursor['destinations'],
                         [{'document': 'fix', 'line': 1},
                          {'document': 'fix', 'line': 2}])

    def test_revoked_mapping_and_broken_chain_cannot_be_substituted(self):
        self.fixture['lineages'].pop('B-reader')
        frame = self._frame({'id': 'a', 'at': 10, 'frames': [100]})
        cursor = sourcejump.navigate_repair(self.fixture, frame)
        self.assertEqual(cursor['decision'], 'repair_lineage_missing')
        self.assertEqual(cursor['origin'], 'B-reader')

        fixture = load_fixture()
        fixture['lineages']['B-reader'] = [
            {'version': 'migrate-1', 'document': 'migrate-1', 'line': 9}]
        frame = sourcejump.navigate_batch(
            fixture, {'id': 'a', 'at': 10, 'frames': [100]})['frames'][0]
        cursor = sourcejump.navigate_repair(fixture, frame)
        self.assertEqual(cursor['decision'], 'repair_lineage_missing')

    def test_partial_symbol_coverage_still_selects_build_from_load_fact(self):
        # plug-K keeps loading; only its debug symbols are absent. The repair
        # cursor for app-B's frame still opens the current editable line.
        self.fixture['symbols'].pop('plug-K')
        result = sourcejump.navigate_batch(self.fixture,
                                           self.fixture['batches'][0])
        cursor = sourcejump.navigate_repair(self.fixture, result['frames'][0])
        self.assertEqual(cursor['decision'], 'repair_cursor')
        self.assertEqual(cursor['cursor']['text'], 'read_repairable_slot()')
        held = sourcejump.navigate_repair(self.fixture, result['frames'][1])
        self.assertEqual(held['decision'], 'repair_symbol_unavailable')

    def test_current_line_hit_does_not_reverse_claim_historical_origin(self):
        # Removing the archived source does not let the workspace line itself
        # stand in for a determined historical build.
        self.fixture['documents'].pop('archive-B')
        result = sourcejump.navigate_batch(self.fixture,
                                           self.fixture['batches'][0])
        frame = result['frames'][0]
        self.assertEqual(frame['decision'], 'source_unavailable')
        self.assertEqual(sourcejump.navigate_repair(self.fixture, frame)
                         ['decision'], 'repair_symbol_unavailable')


class SingleInstantEntryStillWorksTest(unittest.TestCase):
    def test_exact_instant_seed_behaviour_is_unchanged(self):
        seed = json.loads((FIXTURE.parents[1] /
                           'fixtures/profile_nav_normal.json').read_text())
        old, new, plugin = sourcejump.run(seed)
        self.assertEqual(old['stack'][0]['text'], 'read_cached(old_slot)')
        self.assertEqual(new['stack'][0]['text'], 'read_cached(new_slot)')
        self.assertEqual(plugin['build'], 'plug-K')
        self.assertEqual(sourcejump.historical(seed, 10, 200)['decision'],
                         'unmapped_address')
        self.assertEqual(sourcejump.repair(seed, new['stack'][0]['origin'])
                         ['text'], 'read_repairable_slot()')


if __name__ == '__main__':
    unittest.main()
