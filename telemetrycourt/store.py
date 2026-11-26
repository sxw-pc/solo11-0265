import json
import sqlite3
from contextlib import contextmanager

TABLES = ('topologies','requirements','exemptions','exemption_approvals','leases','samples','drifts','blind_cases','escalations','witnesses','alert_labels','events')

def connect(path):
    from . import cover, agent, blind
    db = sqlite3.connect(path, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA busy_timeout=5000')
    db.executescript('CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT UNIQUE,subsystem TEXT,payload TEXT,result TEXT);'+cover.SCHEMA+agent.SCHEMA+blind.SCHEMA)
    return db

@contextmanager
def tx(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.execute('COMMIT')
    except Exception:
        db.execute('ROLLBACK')
        raise

def one(db, sql, args=()):
    row=db.execute(sql,args).fetchone()
    return dict(row) if row else None

def allrows(db, sql, args=()):
    return [dict(r) for r in db.execute(sql,args)]

def run(db, subsystem, command):
    from . import cover, agent, blind
    modules={'cover':cover,'agent':agent,'blind':blind}
    if subsystem not in modules or not command.get('event_id'):
        raise ValueError('subsystem and event_id required')
    payload=json.dumps(command,sort_keys=True,ensure_ascii=False)
    with tx(db):
        prior=one(db,'SELECT * FROM events WHERE event_id=?',(command['event_id'],))
        if prior:
            return json.loads(prior['result']) if prior['payload']==payload and prior['subsystem']==subsystem else {'decision':'event_identity_conflict'}
        result=modules[subsystem].handle(db,command)
        db.execute('INSERT INTO events(event_id,subsystem,payload,result) VALUES(?,?,?,?)',(command['event_id'],subsystem,payload,json.dumps(result,sort_keys=True,ensure_ascii=False)))
        return result

def replay(path):
    source=connect(path)
    target=connect(':memory:')
    mismatches=[]
    events=allrows(source,'SELECT * FROM events ORDER BY seq')
    for event in events:
        actual=run(target,event['subsystem'],json.loads(event['payload']))
        if actual!=json.loads(event['result']):mismatches.append({'event':event['event_id'],'actual':actual})
    for table in TABLES:
        a=[tuple(r) for r in source.execute('SELECT * FROM '+table+' ORDER BY rowid')]
        b=[tuple(r) for r in target.execute('SELECT * FROM '+table+' ORDER BY rowid')]
        if a!=b:mismatches.append({'table':table})
    source.close();target.close()
    return {'verified':not mismatches,'decisions':len(events),'divergences':mismatches}
