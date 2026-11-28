import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from telemetrycourt import probe_review
from telemetrycourt.instrument_vm import execute, LOW, HIGH

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'fixtures'


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def signature(program):
    return [(step['op'], step.get('name')) for step in program]


def exact_value(reading, expression):
    value = 0
    for sign, name in probe_review.parse_expression(expression):
        value += sign * reading[name]
    return value


class ContractMaterialTest(unittest.TestCase):
    def setUp(self):
        self.legacy_contract = load_fixture('probe_contract_legacy.json')
        self.raw_contract = load_fixture('probe_contract_raw.json')
        self.no_relation_contract = load_fixture('probe_contract_raw_no_relation.json')
        self.three_sum_contract = load_fixture('probe_contract_three_sum.json')
        self.legacy = probe_review.issue(self.legacy_contract)
        self.raw = probe_review.issue(self.raw_contract)

    def test_programs_use_only_original_primitives_with_each_input_once(self):
        for certificate in (self.legacy, self.raw):
            inputs = [step['name'] for step in certificate['program'] if step['op'] == 'input']
            self.assertEqual(sorted(inputs), ['a', 'b', 'c'])
            self.assertTrue(all(step['op'] in ('input', 'add', 'subtract')
                                for step in certificate['program']))
            self.assertEqual(len([step for step in certificate['program']
                                  if step['op'] in ('add', 'subtract')]), 2)


class LegacyClipContractTest(ContractMaterialTest):
    def test_legacy_program_is_the_original_fixture_and_keeps_the_named_clip(self):
        fixture = load_fixture('probe_arithmetic_normal.json')
        self.assertEqual(self.legacy['status'], 'signed')
        self.assertEqual(self.legacy['program'], fixture['program'])
        self.assertEqual(self.legacy['named_clips'], [
            {'name': 'historical_a_plus_b', 'expression': 'a+b', 'op': 'add', 'step': 0}])
        # the named clip's exact expression scope is pinned, not renamed later
        self.assertEqual(self.legacy['proof']['node_coefficients'][0], {'a': 1, 'b': 1})
        self.assertEqual(self.legacy['proof']['clipped_steps'], [0])

    def test_legacy_certificate_replays_to_three_and_normal(self):
        result = probe_review.run_certified(self.legacy, {'a': 7, 'b': 4, 'c': 4})
        self.assertEqual(result['status'], 'certified')
        self.assertEqual((result['value'], result['decision']), (3, 'normal'))
        self.assertTrue(result['trace'][0]['clipped'])
        self.assertEqual(result['named_clip_readings'], [
            {'name': 'historical_a_plus_b', 'expression': 'a+b', 'step': 0,
             'stored': 7, 'clipped': True}])
        # the same decision must come from the original review entry, not a table
        direct = probe_review.run({'program': self.legacy['program'],
                                   'inputs': {'a': 7, 'b': 4, 'c': 4},
                                   'limit': self.legacy['limit']})
        self.assertEqual((direct['value'], direct['decision']), (3, 'normal'))

    def test_legacy_acceptance_replays_every_legal_reading_through_the_vm(self):
        domain = probe_review._normalized_domain(self.legacy['domain'])
        self.assertEqual(len(probe_review.domain_points(domain)), 18)
        for reading in probe_review.domain_points(domain):
            replay = execute(self.legacy['program'], reading)
            clipped_steps = {index for index, row in enumerate(replay['trace'])
                             if row['clipped']}
            self.assertEqual(clipped_steps, {0})  # only the named a+b point may saturate
            decision = 'open_review' if replay['value'] >= self.legacy['limit'] else 'normal'
            certified = probe_review.run_certified(self.legacy, reading)
            self.assertEqual(certified['decision'], decision)

    def test_reassociating_across_the_named_point_cannot_represent_the_clip(self):
        reassociated = probe_review._program_nodes(
            [{'op': 'input', 'name': 'a'}, {'op': 'input', 'name': 'b'},
             {'op': 'input', 'name': 'c'}, {'op': 'subtract'}, {'op': 'add'}])
        # a+(b-c) has no add node with scope a+b: the old monitoring point cannot be renamed
        self.assertIsNone(probe_review.named_clip_steps(
            reassociated, self.legacy_contract['named_clips']))
        preserving = probe_review._program_nodes(self.legacy['program'])
        self.assertEqual(probe_review.named_clip_steps(
            preserving, self.legacy_contract['named_clips']),
            {'historical_a_plus_b': 0})
        evidence, failure = probe_review._evaluate_candidate(
            [{'op': 'input', 'name': 'a'}, {'op': 'input', 'name': 'b'},
             {'op': 'input', 'name': 'c'}, {'op': 'subtract'}, {'op': 'add'}],
            reassociated, {'a': 1, 'b': 1, 'c': -1},
            probe_review._normalized_domain(self.legacy_contract),
            'legacy_clip', self.legacy_contract['named_clips'])
        self.assertIsNone(evidence)
        self.assertEqual(failure['reason'], 'named_clip_not_representable')


class RawExactContractTest(ContractMaterialTest):
    def test_raw_program_groups_b_minus_c_first_and_signs_via_relations(self):
        self.assertEqual(self.raw['status'], 'signed')
        self.assertEqual(signature(self.raw['program']),
                         [('input', 'a'), ('input', 'b'), ('input', 'c'),
                          ('subtract', None), ('add', None)])
        self.assertEqual(self.raw['proof']['node_coefficients'][0], {'b': 1, 'c': -1})
        self.assertEqual(self.raw['proof']['clipped_steps'], [])
        # independent per-sensor boxes would falsely reject it; the relation proves safety
        self.assertFalse(self.raw['independent_box']['signable_without_relations'])

    def test_raw_certificate_replays_to_seven_and_open_review(self):
        result = probe_review.run_certified(self.raw, {'a': 7, 'b': 4, 'c': 4})
        self.assertEqual(result['status'], 'certified')
        self.assertEqual((result['value'], result['decision']), (7, 'open_review'))
        self.assertTrue(all(not row['clipped'] for row in result['trace']))

    def test_fixed_program_is_exact_over_the_whole_legal_relation_domain(self):
        domain = probe_review._normalized_domain(self.raw['domain'])
        points = probe_review.domain_points(domain)
        self.assertEqual(len(points), 18)
        for reading in points:
            replay = execute(self.raw['program'], reading)
            self.assertEqual(replay['value'], exact_value(reading, 'a+b-c'))
            self.assertTrue(all(not row['clipped'] for row in replay['trace']))
            for row in replay['trace']:
                self.assertTrue(LOW <= row['stored'] <= HIGH)
        self.assertEqual(self.raw['proof']['exact_target_range'], [3, 7])
        self.assertEqual(self.raw['proof']['stored_ranges'], {'0': [-2, 0], '1': [3, 7]})

    def test_grouped_relation_domain_can_sign_even_though_boxes_alone_do_not(self):
        grouped_contract = {
            'id': 'grouped-raw', 'kind': 'raw_exact', 'expression': 'a+b-c', 'limit': 6,
            'groups': [
                {'inputs': {'a': [6, 7], 'b': [3, 4], 'c': [3, 4]},
                 'relations': [{'op': '>=', 'left': 'c', 'right': 'b'}]},
                {'inputs': {'a': [5, 5], 'b': [5, 5], 'c': [5, 5]}, 'relations': []}]}
        certificate = probe_review.issue(grouped_contract)
        self.assertEqual(certificate['status'], 'signed')
        # a reading mixing group one's a with group two's b/c is not part of the signed domain
        mixed = probe_review.run_certified(certificate, {'a': 6, 'b': 5, 'c': 5})
        self.assertEqual((mixed['status'], mixed['reason']),
                         ('held_for_review', 'outside_signed_relation_domain'))
        legal = probe_review.run_certified(certificate, {'a': 5, 'b': 5, 'c': 5})
        self.assertEqual(legal['status'], 'certified')


class NoRelationRefusalTest(ContractMaterialTest):
    def setUp(self):
        super().setUp()
        self.refusal = probe_review.issue(self.no_relation_contract)

    def test_removing_c_ge_b_refuses_with_the_exact_register_overflow_values(self):
        self.assertEqual(self.refusal['status'], 'refused')
        overflow = self.refusal['register_overflow']
        self.assertEqual([(item['reading'], item['exact']) for item in overflow], [
            ({'a': 6, 'b': 5, 'c': 3}, 8),
            ({'a': 7, 'b': 4, 'c': 3}, 8),
            ({'a': 7, 'b': 5, 'c': 3}, 9),
            ({'a': 7, 'b': 5, 'c': 4}, 8)])
        self.assertTrue(all(item['exact'] > HIGH for item in overflow))
        self.assertEqual(len(self.refusal['unsigned_domain']), 27)
        self.assertEqual(self.refusal['final_exact_range'], [3, 9])

    def test_refusal_artifact_is_runnable_and_replays_through_the_vm(self):
        ok, checked = probe_review.verify_artifact(self.refusal)
        self.assertTrue(ok)
        self.assertEqual(len(checked), len(self.refusal['candidates']))
        for candidate in self.refusal['candidates']:
            failure = candidate['failure']
            replay = execute(candidate['program'], failure['reading'])
            self.assertEqual(replay, failure['replay'])
            self.assertNotEqual(replay['value'], failure['exact'])

    def test_the_signed_relation_program_is_among_the_failing_candidates_without_relation(self):
        programs = [signature(candidate['program']) for candidate in self.refusal['candidates']]
        self.assertIn(signature(self.raw['program']), programs)


class ThreeSumGroupedRefusalTest(ContractMaterialTest):
    def setUp(self):
        super().setUp()
        self.refusal = probe_review.issue(self.three_sum_contract)
        self.domain = probe_review._normalized_domain(self.three_sum_contract)

    def test_groups_union_without_cross_mixing(self):
        points = probe_review.domain_points(self.domain)
        self.assertEqual(len(points), 9)  # 3 groups x 3 values, not 27 cross products
        self.assertFalse(probe_review.domain_contains(
            self.domain, {'a': -5, 'b': 5, 'c': 6}))
        self.assertTrue(probe_review.domain_contains(
            self.domain, {'a': -7, 'b': 6, 'c': 6}))

    def test_every_final_truth_fits_but_every_first_group_has_a_saturating_witness(self):
        self.assertEqual(self.refusal['status'], 'refused')
        self.assertEqual(self.refusal['final_exact_range'], [5, 7])
        self.assertEqual(self.refusal['register_overflow'], [])
        witnesses = self.refusal['first_group_witnesses']
        self.assertEqual(set(witnesses), {'ab', 'ac', 'bc'})
        for key, reading in witnesses.items():
            self.assertTrue(probe_review.domain_contains(self.domain, reading))

    def test_no_fixed_program_survives_full_domain_replay(self):
        for candidate in self.refusal['candidates']:
            reading = candidate['failure']['reading']
            replay = execute(candidate['program'], reading)
            self.assertTrue(replay['trace'][0]['clipped'])
            self.assertNotEqual(replay['value'], exact_value(reading, 'a+b+c'))
        ok, checked = probe_review.verify_artifact(self.refusal)
        self.assertTrue(ok)
        self.assertEqual(len(checked), len(self.refusal['candidates']))
        # the given example alone is not enough: every candidate must fail on some legal point
        self.assertGreaterEqual(len(self.refusal['candidates']), 3)


class CertifiedRuntimeTest(ContractMaterialTest):
    def test_readings_violating_signed_relations_are_held_without_a_review_decision(self):
        for reading, reason in [
            ({'a': 7, 'b': 5, 'c': 3}, 'outside_signed_relation_domain'),
            ({'a': 7, 'b': 4}, 'reading_input_mismatch'),
            ({'a': 9, 'b': 4, 'c': 4}, 'reading_outside_register'),
        ]:
            held = probe_review.run_certified(self.raw, reading)
            self.assertEqual(held['status'], 'held_for_review')
            self.assertEqual(held['reason'], reason)
            self.assertNotIn('decision', held)
            self.assertNotIn('value', held)

    def test_certificate_binds_program_domain_and_threshold_together(self):
        tampered = dict(self.raw)
        tampered['program'] = [
            {'op': 'input', 'name': 'a'}, {'op': 'input', 'name': 'b'}, {'op': 'add'},
            {'op': 'input', 'name': 'c'}, {'op': 'subtract'}]
        # (a+b)-c saturates early on a legal reading; the certificate must not endorse it
        guarded = probe_review.run_certified(tampered, {'a': 5, 'b': 3, 'c': 3})
        self.assertEqual(guarded['status'], 'held_for_review')
        self.assertEqual(guarded['reason'], 'certificate_integrity_failure')

    def test_held_reading_is_not_combined_with_legacy_certificate_threshold(self):
        held = probe_review.run_certified(self.legacy, {'a': 7, 'b': 5, 'c': 3})
        self.assertEqual(held['status'], 'held_for_review')
        self.assertNotIn('decision', held)
        legal = probe_review.run_certified(self.legacy, {'a': 7, 'b': 4, 'c': 4})
        self.assertEqual(legal['decision'], 'normal')


class ContractValidationTest(unittest.TestCase):
    def base(self, **overrides):
        contract = {'id': 'x', 'kind': 'raw_exact', 'expression': 'a+b-c', 'limit': 6,
                    'inputs': {'a': [5, 7], 'b': [3, 5], 'c': [3, 5]},
                    'relations': [{'op': '>=', 'left': 'c', 'right': 'b'}]}
        contract.update(overrides)
        return contract

    def test_expressions_reject_constants_and_repeated_inputs(self):
        with self.assertRaises(ValueError):
            probe_review.parse_expression('a+1-c')
        with self.assertRaises(ValueError):
            probe_review.parse_expression('a+b-a')
        self.assertEqual(probe_review.parse_expression('-a+b'), [(-1, 'a'), (1, 'b')])

    def test_limits_on_inputs_and_named_clips(self):
        with self.assertRaises(ValueError):
            probe_review.issue(self.base(expression='a+b+c+d+e+f'))
        with self.assertRaises(ValueError):
            probe_review.issue(self.base(
                kind='legacy_clip',
                named_clips=[{'name': f'p{i}', 'expression': 'a+b', 'op': 'add'}
                             for i in range(3)]))
        with self.assertRaises(ValueError):
            probe_review.issue(self.base(named_clips=[
                {'name': 'p', 'expression': 'a+b', 'op': 'add'}]))
        with self.assertRaises(ValueError):
            probe_review.issue(self.base(
                kind='legacy_clip', named_clips=[]))

    def test_empty_relation_domain_is_rejected(self):
        impossible = self.base(relations=[
            {'op': '>=', 'left': 'c', 'right': 'b'},
            {'op': '>', 'left': 'b', 'right': 'c'}])
        with self.assertRaises(ValueError):
            probe_review.issue(impossible)


class CommandLineEntryTest(unittest.TestCase):
    def run_cli(self, *arguments):
        argv = repr(['telemetrycourt', 'probe-formula', *arguments])
        bootstrap = (
            "import sys; "
            f"sys.path.insert(0, {str(ROOT)!r}); "
            "from telemetrycourt.__main__ import main; "
            f"sys.argv = {argv}; main()")
        return subprocess.run(
            [sys.executable, '-I', '-c', bootstrap],
            cwd=ROOT, capture_output=True, text=True)

    def test_issue_and_certified_run_and_hold_are_executable(self):
        signed = self.run_cli('--fixture', 'fixtures/probe_contract_raw.json')
        self.assertEqual(signed.returncode, 0)
        certificate = json.loads(signed.stdout)
        self.assertEqual(certificate['status'], 'signed')
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as handle:
            json.dump(certificate, handle)
            cert_path = handle.name
        try:
            good = self.run_cli(
                '--fixture', 'fixtures/probe_reading_in_relation.json',
                '--certificate', cert_path,
                '--reading', 'fixtures/probe_reading_in_relation.json')
            self.assertEqual(good.returncode, 0)
            self.assertEqual(json.loads(good.stdout)['decision'], 'open_review')

            held = self.run_cli(
                '--fixture', 'fixtures/probe_reading_violates_relation.json',
                '--certificate', cert_path,
                '--reading', 'fixtures/probe_reading_violates_relation.json')
            self.assertEqual(held.returncode, 3)
            self.assertEqual(json.loads(held.stdout)['status'], 'held_for_review')
        finally:
            os.unlink(cert_path)

        refused = self.run_cli('--fixture', 'fixtures/probe_contract_three_sum.json')
        self.assertEqual(refused.returncode, 2)
        self.assertEqual(json.loads(refused.stdout)['status'], 'refused')


if __name__ == '__main__':
    unittest.main()
