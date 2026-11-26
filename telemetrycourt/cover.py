from .store import one,allrows

SCHEMA='''
CREATE TABLE IF NOT EXISTS topologies(object TEXT PRIMARY KEY,uid TEXT,service TEXT,generation INTEGER,observed INTEGER);
CREATE TABLE IF NOT EXISTS requirements(id TEXT PRIMARY KEY,object TEXT,signal TEXT,generation INTEGER,min_sources INTEGER,max_gap INTEGER,severity TEXT,effective INTEGER,status TEXT);
CREATE TABLE IF NOT EXISTS exemptions(id TEXT PRIMARY KEY,object TEXT,signal TEXT,start INTEGER,expires INTEGER,reason TEXT,status TEXT);
CREATE TABLE IF NOT EXISTS exemption_approvals(id TEXT PRIMARY KEY,exemption TEXT,actor TEXT,role TEXT,expires INTEGER);
'''

def handle(db,x):
    op=x['op']
    if op=='topology':
        old=one(db,'SELECT * FROM topologies WHERE object=?',(x['object'],))
        if old and x['generation']<=old['generation']:
            same=all(old[k]==x[k] for k in ('uid','service','generation'))
            return {'decision':'reused' if same else 'stale_topology'}
        db.execute('INSERT INTO topologies VALUES(?,?,?,?,?) ON CONFLICT(object) DO UPDATE SET uid=excluded.uid,service=excluded.service,generation=excluded.generation,observed=excluded.observed',(x['object'],x['uid'],x['service'],x['generation'],x['at']))
        if old:
            db.execute("UPDATE leases SET status='stale' WHERE object=? AND object_uid<>? AND status='active'",(x['object'],x['uid']))
            db.execute("UPDATE blind_cases SET status='review' WHERE object=? AND status IN ('open','suppressed')",(x['object'],))
        return {'decision':'topology_recorded','uid':x['uid']}
    if op=='requirement':
        top=one(db,'SELECT * FROM topologies WHERE object=?',(x['object'],))
        old=one(db,'SELECT * FROM requirements WHERE id=?',(x['id'],))
        if not top or x['min_sources']<1 or x['max_gap']<1 or x['severity'] not in ('normal','critical'):
            return {'decision':'invalid_requirement'}
        if old and (old['object'],old['signal'])!=(x['object'],x['signal']):
            return {'decision':'requirement_identity_conflict'}
        if old and x['generation']<=old['generation']:
            return {'decision':'stale_requirement'}
        db.execute('INSERT INTO requirements VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET generation=excluded.generation,min_sources=excluded.min_sources,max_gap=excluded.max_gap,severity=excluded.severity,effective=excluded.effective,status=excluded.status',(x['id'],x['object'],x['signal'],x['generation'],x['min_sources'],x['max_gap'],x['severity'],x['effective'],'active'))
        return {'decision':'requirement_active'}
    if op=='exemption':
        req=one(db,'SELECT * FROM requirements WHERE object=? AND signal=? AND status=?',(x['object'],x['signal'],'active'))
        if not req or x['expires']<=x['start']:
            return {'decision':'invalid_exemption'}
        db.execute('INSERT INTO exemptions VALUES(?,?,?,?,?,?,?)',(x['id'],x['object'],x['signal'],x['start'],x['expires'],x['reason'],'pending'))
        return {'decision':'exemption_pending'}
    if op=='approve':
        exemption=one(db,'SELECT * FROM exemptions WHERE id=?',(x['exemption'],))
        if not exemption or exemption['status']!='pending' or x['role'] not in ('oncall','owner') or x['expires']<exemption['expires']:
            return {'decision':'approval_denied'}
        db.execute('INSERT INTO exemption_approvals VALUES(?,?,?,?,?)',(x['id'],x['exemption'],x['actor'],x['role'],x['expires']))
        votes=allrows(db,'SELECT actor,role FROM exemption_approvals WHERE exemption=?',(x['exemption'],))
        if len({v['role'] for v in votes})==2 and len({v['actor'] for v in votes})==2:
            db.execute("UPDATE exemptions SET status='active' WHERE id=?",(x['exemption'],))
            return {'decision':'exemption_active'}
        return {'decision':'approval_recorded'}
    if op=='revoke_exemption':
        e=one(db,'SELECT * FROM exemptions WHERE id=?',(x['id'],))
        if not e or e['status']!='active':return {'decision':'not_active'}
        db.execute("UPDATE exemptions SET status='revoked' WHERE id=?",(x['id'],))
        return {'decision':'exemption_revoked'}
    return {'decision':'unknown_operation'}
