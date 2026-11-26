from .store import one,allrows

SCHEMA='''
CREATE TABLE IF NOT EXISTS blind_cases(id TEXT PRIMARY KEY,object TEXT,object_uid TEXT,signal TEXT,requirement TEXT,requirement_generation INTEGER,min_sources INTEGER,max_gap INTEGER,start INTEGER,end INTEGER,status TEXT,reason TEXT);
CREATE TABLE IF NOT EXISTS escalations(id TEXT PRIMARY KEY,case_id TEXT,owner TEXT,at INTEGER,status TEXT);
CREATE TABLE IF NOT EXISTS witnesses(id TEXT PRIMARY KEY,case_id TEXT,actor TEXT,at INTEGER,kind TEXT);
CREATE TABLE IF NOT EXISTS alert_labels(id TEXT PRIMARY KEY,case_id TEXT,alert TEXT,label TEXT,at INTEGER);
'''

def coverage(db,req,start,end):
    top=one(db,'SELECT * FROM topologies WHERE object=?',(req['object'],))
    if not top:return False
    samples=allrows(db,"SELECT s.* FROM samples s JOIN leases l ON l.id=s.lease WHERE s.object=? AND s.signal=? AND s.status='trusted' AND l.status='active' AND l.object_uid=? AND l.agent_uid=s.agent_uid AND s.corrected_at BETWEEN ? AND ? ORDER BY s.corrected_at",(req['object'],req['signal'],top['uid'],start,end))
    sources={s['source'] for s in samples}
    if len(sources)<req['min_sources']:return False
    times=sorted({start,*[s['corrected_at'] for s in samples],end})
    return all(b-a<=req['max_gap'] for a,b in zip(times,times[1:]))

def handle(db,x):
    op=x['op']
    if op=='assess':
        req=one(db,'SELECT * FROM requirements WHERE id=?',(x['requirement'],))
        top=one(db,'SELECT * FROM topologies WHERE object=?',(req['object'],)) if req else None
        if not req or not top or x['end']<=x['start'] or x['start']<req['effective']:
            return {'decision':'invalid_window'}
        if coverage(db,req,x['start'],x['end']):return {'decision':'coverage_trusted'}
        exemption=one(db,"SELECT * FROM exemptions WHERE object=? AND signal=? AND status='active' AND start<=? AND expires>=? ORDER BY expires DESC LIMIT 1",(req['object'],req['signal'],x['start'],x['end']))
        status='suppressed' if exemption else 'open'
        db.execute('INSERT INTO blind_cases VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(x['id'],req['object'],top['uid'],req['signal'],req['id'],req['generation'],req['min_sources'],req['max_gap'],x['start'],x['end'],status,'maintenance' if exemption else 'missing_coverage'))
        return {'decision':'maintenance_suppressed' if exemption else 'blind_escalate','case':x['id']}
    if op=='escalate':
        case=one(db,'SELECT * FROM blind_cases WHERE id=?',(x['case'],))
        if not case or case['status'] not in ('open','review'):
            return {'decision':'not_escalatable'}
        db.execute('INSERT INTO escalations VALUES(?,?,?,?,?)',(x['id'],x['case'],x['owner'],x['at'],'active'))
        return {'decision':'oncall_assigned'}
    if op=='handoff':
        old=one(db,'SELECT * FROM escalations WHERE id=?',(x['from'],))
        if not old or old['status']!='active' or x['at']<=old['at']:
            return {'decision':'handoff_denied'}
        db.execute("UPDATE escalations SET status='handed_off' WHERE id=?",(x['from'],))
        db.execute('INSERT INTO escalations VALUES(?,?,?,?,?)',(x['id'],old['case_id'],x['owner'],x['at'],'active'))
        return {'decision':'oncall_handed_off'}
    if op=='label':
        case=one(db,'SELECT * FROM blind_cases WHERE id=?',(x['case'],))
        if not case:return {'decision':'unknown_case'}
        label='signal_insufficient' if case['status'] in ('open','review') else 'maintenance_suppressed' if case['status']=='suppressed' else 'recovered'
        db.execute('INSERT INTO alert_labels VALUES(?,?,?,?,?)',(x['id'],x['case'],x['alert'],label,x['at']))
        return {'decision':label}
    if op=='witness':
        case=one(db,'SELECT * FROM blind_cases WHERE id=?',(x['case'],))
        if not case or x['kind'] not in ('independent','owner'):
            return {'decision':'witness_denied'}
        db.execute('INSERT INTO witnesses VALUES(?,?,?,?,?)',(x['id'],x['case'],x['actor'],x['at'],x['kind']))
        return {'decision':'witness_recorded'}
    if op=='close':
        case=one(db,'SELECT * FROM blind_cases WHERE id=?',(x['case'],))
        if not case or case['status'] not in ('open','review','suppressed'):
            return {'decision':'not_open'}
        top=one(db,'SELECT * FROM topologies WHERE object=?',(case['object'],))
        req=case
        witness=one(db,"SELECT * FROM witnesses WHERE case_id=? AND kind='independent' ORDER BY at DESC LIMIT 1",(x['case'],))
        if not top or top['uid']!=case['object_uid'] or not req or not witness or x['end']<=x['start'] or not coverage(db,req,x['start'],x['end']):
            return {'decision':'recovery_unproven'}
        db.execute("UPDATE blind_cases SET status='closed' WHERE id=?",(x['case'],))
        db.execute("UPDATE escalations SET status='closed' WHERE case_id=? AND status='active'",(x['case'],))
        return {'decision':'blind_closed'}
    return {'decision':'unknown_operation'}
