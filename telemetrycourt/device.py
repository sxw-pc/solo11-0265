"""Persist a running synthetic diagnostic device and open its captured details."""
import json

from . import burst, capture
from .store import one, tx

SCHEMA = """CREATE TABLE IF NOT EXISTS capture_devices (
    name TEXT PRIMARY KEY, revision TEXT NOT NULL, threshold INTEGER NOT NULL,
    last_tick INTEGER NOT NULL, checkpoint TEXT NOT NULL);"""


def run(db, action):
    db.executescript(SCHEMA + capture.SCHEMA)
    device = action['device']
    with tx(db):
        row = one(db, 'SELECT * FROM capture_devices WHERE name=?', (device,))
        op = action['op']
        if op == 'open':
            return capture.open_detail(db, device, action['handle'])
        if op == 'configure':
            if row is not None:
                return {'decision': 'already_configured'}
            initial = dict(streak=0, opened_at=None, fired=False, remaining=0, captures={})
            db.execute('INSERT INTO capture_devices VALUES(?,?,?,-1,?)',
                       (device, action['revision'], action['threshold'], json.dumps(initial)))
            return {'decision': 'configured'}
        if row is None:
            return {'decision': 'unknown_device'}
        state = json.loads(row['checkpoint'])
        if op == 'checkpoint':
            return dict(state=state, revision=row['revision'], last_tick=row['last_tick'])
        if op == 'enable':
            state['remaining'] = action['space']
            db.execute('UPDATE capture_devices SET checkpoint=? WHERE name=?', (json.dumps(state), device))
            return {'decision': 'recording_enabled'}
        if op == 'ack':
            if action['revision'] != row['revision']:
                return {'decision': 'stale_revision'}
            detail = capture.open_detail(db, device, action['handle'])
            if detail and detail['sample'] == action['sample']:
                return {'decision': 'existing_detail'}
            return {'decision': 'unknown_detail'}
        if op != 'receive':
            raise ValueError('unknown device operation')
        sample = action['sample']
        if sample['tick'] <= row['last_tick']:
            return {'decision': 'stale_tick'}
        decision = burst.advance(state, sample, row['threshold'])
        result = {'decision': decision}
        if decision == 'captured':
            result['handle'] = capture.persist_detail(db, device, row['revision'], state['opened_at'], sample)
        db.execute('UPDATE capture_devices SET checkpoint=?, last_tick=? WHERE name=?',
                   (json.dumps(state), sample['tick'], device))
        return result
