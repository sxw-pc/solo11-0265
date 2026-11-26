import json
import tempfile
import unittest
from pathlib import Path
import telemetrycourt
from telemetrycourt.store import connect,run,replay,one

ROOT=Path(__file__).resolve().parents[1]

class TelemetryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'state.sqlite'
        self.db=connect(str(self.path))
    def tearDown(self):
        self.db.close();self.temp.cleanup()
    def fixture(self,sub,kind):
        commands=json.loads((ROOT/'fixtures'/f'{sub}_{kind}.json').read_text(encoding='utf-8'))
        return [run(self.db,sub,x) for x in commands]
    def start(self):
        self.fixture('cover','normal');self.fixture('agent','normal')
    def test_cover_contract_and_maintenance_need_two_roles(self):
        results=self.fixture('cover','normal')
        self.assertEqual(results[-1]['decision'],'exemption_active')
        self.assertEqual(one(self.db,"SELECT status FROM exemptions WHERE id='maintenance-a'")['status'],'active')
        self.assertEqual(self.fixture('cover','failure')[0]['decision'],'stale_topology')
    def test_trusted_coverage_and_blind_escalation_are_distinct(self):
        self.start()
        self.assertEqual(self.fixture('blind','normal')[0]['decision'],'coverage_trusted')
        self.assertEqual(one(self.db,"SELECT status FROM blind_cases WHERE id='case-1'")['status'],'open')
        self.assertEqual(one(self.db,"SELECT status FROM blind_cases WHERE id='case-2'")['status'],'suppressed')
        self.assertEqual(one(self.db,"SELECT owner FROM escalations WHERE status='active'")['owner'],'bob')
    def test_expired_exemption_escalates_and_recovery_requires_continuity(self):
        self.start();self.fixture('blind','normal')
        self.assertEqual(run(self.db,'blind',{'event_id':'early-close','op':'close','case':'case-1','start':40,'end':50})['decision'],'recovery_unproven')
        self.fixture('agent','failure')
        self.assertEqual(self.fixture('blind','failure')[0]['decision'],'blind_closed')
        self.assertEqual(one(self.db,"SELECT status FROM blind_cases WHERE id='case-expired'")['status'],'open')
    def test_topology_rebuild_invalidates_old_agent_coverage(self):
        self.start()
        self.assertEqual(run(self.db,'cover',{'event_id':'new-top','op':'topology','object':'svc-a','uid':'uid-2','service':'checkout','generation':2,'at':31})['decision'],'topology_recorded')
        self.assertEqual(run(self.db,'agent',{'event_id':'late-old','op':'sample','id':'late-old','lease':'lease-a','object':'svc-a','signal':'latency','source':'node-agent','agent_uid':'agent-1','at':32,'sequence':4})['decision'],'untrusted_sample')
        self.assertEqual(run(self.db,'blind',{'event_id':'new-case','op':'assess','id':'new-case','requirement':'req-a','start':31,'end':41})['decision'],'blind_escalate')
    def test_drift_isolates_samples_and_reopens_closed_case(self):
        self.start();self.fixture('blind','normal');self.fixture('agent','failure');self.fixture('blind','failure')
        result=run(self.db,'agent',{'event_id':'late-drift','op':'drift','id':'late-drift','lease':'lease-a','offset':30,'max_abs':5,'generation':1,'at':60})
        self.assertEqual(result['decision'],'drift_isolated')
        self.assertEqual(one(self.db,"SELECT status FROM blind_cases WHERE id='case-1'")['status'],'review')
    def test_two_sources_cannot_share_one_agent_identity(self):
        self.start()
        lease={'event_id':'shared-source','op':'lease','id':'lease-shared','object':'svc-a','object_uid':'uid-1','agent_uid':'agent-1','source':'sidecar','node_generation':1,'lease_generation':1,'start':0,'expires':100}
        self.assertEqual(run(self.db,'agent',lease)['decision'],'source_not_independent')
        req={'event_id':'req-2','op':'requirement','id':'req-a','object':'svc-a','signal':'latency','generation':2,'min_sources':2,'max_gap':10,'severity':'critical','effective':0}
        self.assertEqual(run(self.db,'cover',req)['decision'],'requirement_active')
        self.assertEqual(run(self.db,'blind',{'event_id':'two-source-case','op':'assess','id':'two-source-case','requirement':'req-a','start':10,'end':30})['decision'],'blind_escalate')
    def test_case_keeps_original_requirement_when_policy_changes(self):
        self.start();self.fixture('blind','normal')
        req={'event_id':'relax','op':'requirement','id':'req-a','object':'svc-a','signal':'latency','generation':2,'min_sources':1,'max_gap':100,'severity':'critical','effective':0}
        self.assertEqual(run(self.db,'cover',req)['decision'],'requirement_active')
        case=one(self.db,"SELECT * FROM blind_cases WHERE id='case-1'")
        self.assertEqual((case['requirement_generation'],case['max_gap']),(1,10))
        self.assertEqual(run(self.db,'blind',{'event_id':'relaxed-new','op':'assess','id':'relaxed-new','requirement':'req-a','start':10,'end':50})['decision'],'coverage_trusted')
        self.assertEqual(one(self.db,"SELECT status FROM blind_cases WHERE id='case-1'")['status'],'open')
    def test_duplicate_event_conflict_and_full_replay(self):
        for sub,kind in [('cover','normal'),('agent','normal'),('blind','normal'),('cover','failure'),('agent','failure'),('blind','failure')]:self.fixture(sub,kind)
        event=json.loads((ROOT/'fixtures'/'cover_normal.json').read_text(encoding='utf-8'))[0]
        self.assertEqual(run(self.db,'cover',event)['decision'],'topology_recorded')
        self.assertEqual(run(self.db,'cover',dict(event,uid='forged'))['decision'],'event_identity_conflict')
        result=replay(str(self.path))
        self.assertTrue(result['verified'],result['divergences'])
        self.assertEqual(result['decisions'],30)
    def test_imports_current_repository(self):
        self.assertEqual(Path(telemetrycourt.__file__).resolve().parents[1],ROOT)

print('module_file',telemetrycourt.__file__)
