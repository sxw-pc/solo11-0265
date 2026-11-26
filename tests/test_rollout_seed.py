import unittest

from telemetrycourt import rollout, store


class RolloutTest(unittest.TestCase):
    def test_real_pairs_change_the_active_route(self):
        fixture = dict(route='route-diagnostics', candidate='updated', planned=3,
                       false_release_limit='7/50', pairs=[
                           dict(position=position, base_ms=2, candidate_ms=1)
                           for position in range(1, 4)])
        db = store.connect(':memory:')
        try:
            prefix = rollout.run(db, {**fixture, 'pairs': fixture['pairs'][:2]})
            self.assertEqual(prefix['decision'], 'collect_more')
            self.assertEqual(prefix['next_collector'], 'baseline')
            modified = {**fixture['pairs'][-1], 'candidate_ms': 3}
            hold = rollout.run(db, {**fixture, 'pairs': fixture['pairs'][:-1] + [modified]})
            self.assertEqual(hold['next_collector'], 'baseline')
            self.assertEqual(hold['risk'], '1/2')
            released = rollout.run(db, fixture)
            self.assertEqual(released['next_collector'], 'updated')
            self.assertEqual(released['risk'], '1/8')
        finally:
            db.close()
