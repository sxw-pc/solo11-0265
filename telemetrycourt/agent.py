from .store import one,allrows

SCHEMA='''
CREATE TABLE IF NOT EXISTS leases(id TEXT PRIMARY KEY,object TEXT,object_uid TEXT,agent_uid TEXT,source TEXT,node_generation INTEGER,lease_generation INTEGER,start INTEGER,expires INTEGER,status TEXT);
CREATE TABLE IF NOT EXISTS samples(id TEXT PRIMARY KEY,lease TEXT,object TEXT,signal TEXT,source TEXT,agent_uid TEXT,raw_at INTEGER,corrected_at INTEGER,sequence INTEGER,status TEXT);
CREATE TABLE IF NOT EXISTS drifts(id TEXT PRIMARY KEY,lease TEXT,offset INTEGER,max_abs INTEGER,generation INTEGER,at INTEGER);
'''

def handle(db,x):
    op=x['op']
    if op=='lease':
        top=one(db,'SELECT * FROM topologies WHERE object=?',(x['object'],))
        old=one(db,'SELECT * FROM leases WHERE id=?',(x['id'],))
        if not top or top['uid']!=x['object_uid'] or x['expires']<=x['start']:
            return {'decision':'lease_denied'}
        if old and (old['object'],old['object_uid'])!=(x['object'],x['object_uid']):
            return {'decision':'lease_identity_conflict'}
        other=one(db,"SELECT 1 FROM leases WHERE object=? AND agent_uid=? AND source<>? AND status='active' AND id<>?",(x['object'],x['agent_uid'],x['source'],x['id']))
        if other:return {'decision':'source_not_independent'}
        if old and x['lease_generation']<=old['lease_generation']:
            return {'decision':'stale_lease'}
        db.execute('INSERT INTO leases VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET agent_uid=excluded.agent_uid,source=excluded.source,node_generation=excluded.node_generation,lease_generation=excluded.lease_generation,start=excluded.start,expires=excluded.expires,status=excluded.status',(x['id'],x['object'],x['object_uid'],x['agent_uid'],x['source'],x['node_generation'],x['lease_generation'],x['start'],x['expires'],'active'))
        return {'decision':'lease_active'}
    if op=='drift':
        lease=one(db,'SELECT * FROM leases WHERE id=?',(x['lease'],))
        old=one(db,'SELECT * FROM drifts WHERE lease=? ORDER BY generation DESC LIMIT 1',(x['lease'],))
        if not lease or (old and x['generation']<=old['generation']) or x['max_abs']<0:
            return {'decision':'drift_denied'}
        db.execute('INSERT INTO drifts VALUES(?,?,?,?,?,?)',(x['id'],x['lease'],x['offset'],x['max_abs'],x['generation'],x['at']))
        if abs(x['offset'])>x['max_abs']:
            db.execute("UPDATE samples SET status='isolated' WHERE lease=? AND status='trusted'",(x['lease'],))
            db.execute("UPDATE blind_cases SET status='review',reason='drift_reopened' WHERE object=? AND status='closed' AND EXISTS (SELECT 1 FROM samples WHERE lease=? AND corrected_at BETWEEN blind_cases.start AND blind_cases.end)",(lease['object'],x['lease']))
            return {'decision':'drift_isolated'}
        return {'decision':'drift_accepted'}
    if op=='sample':
        lease=one(db,'SELECT * FROM leases WHERE id=?',(x['lease'],))
        top=one(db,'SELECT * FROM topologies WHERE object=?',(x['object'],))
        req=one(db,"SELECT * FROM requirements WHERE object=? AND signal=? AND status='active' ORDER BY generation DESC LIMIT 1",(x['object'],x['signal']))
        if not lease or not top or not req or lease['status']!='active' or lease['object']!=x['object'] or lease['object_uid']!=top['uid'] or lease['agent_uid']!=x['agent_uid'] or lease['source']!=x['source'] or not lease['start']<=x['at']<lease['expires']:
            return {'decision':'untrusted_sample'}
        prior=one(db,'SELECT MAX(sequence) n FROM samples WHERE lease=?',(x['lease'],))
        if prior['n'] is not None and x['sequence']<=prior['n']:
            return {'decision':'stale_sequence'}
        drift=one(db,'SELECT * FROM drifts WHERE lease=? ORDER BY generation DESC LIMIT 1',(x['lease'],))
        corrected=x['at']-(drift['offset'] if drift else 0)
        if not lease['start']<=corrected<lease['expires']:
            return {'decision':'corrected_time_outside_lease'}
        status='isolated' if drift and abs(drift['offset'])>drift['max_abs'] else 'trusted'
        db.execute('INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?,?)',(x['id'],x['lease'],x['object'],x['signal'],x['source'],x['agent_uid'],x['at'],corrected,x['sequence'],status))
        return {'decision':'sample_isolated' if status=='isolated' else 'sample_trusted','corrected_at':corrected}
    if op=='interval':
        req=one(db,"SELECT * FROM requirements WHERE object=? AND signal=? AND status='active' ORDER BY generation DESC LIMIT 1",(x['object'],x['signal']))
        if not req:return {'decision':'no_requirement'}
        if x['end']<=x['start'] or x['start']<req['effective']:
            return {'decision':'invalid_window'}
        from .blind import coverage_evidence
        covered,samples=coverage_evidence(db,req,x['start'],x['end'])
        return {'decision':'covered' if covered else 'undercovered','sources':len({s['source'] for s in samples})}
    return {'decision':'unknown_operation'}
