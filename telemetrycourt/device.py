"""Persist a running synthetic diagnostic device and open its captured details."""
import json

from . import burst, capture
from .store import one, tx

SCHEMA = """CREATE TABLE IF NOT EXISTS capture_devices (
    name TEXT PRIMARY KEY, revision TEXT NOT NULL, threshold INTEGER NOT NULL,
    last_tick INTEGER NOT NULL, checkpoint TEXT NOT NULL,
    pending_revision TEXT, pending_threshold INTEGER);"""


def _pending(row):
    if row['pending_revision'] is None:
        return None
    return dict(revision=row['pending_revision'], threshold=row['pending_threshold'])


def _pin_count(catalog, state, threshold, last_tick):
    """Exact high count a raw catalog proves for the open segment, else None.

    A catalog pins the segment only when it replays every high from the
    segment head up to the last received tick and lands on the checkpoint
    the old rule actually left behind; a partial catalog pins nothing.
    """
    if not isinstance(catalog, list) or not catalog:
        return None
    previous = -1
    for sample in catalog:
        if not isinstance(sample, dict) or sample.get('high') is not True:
            return None
        tick = sample.get('tick')
        if type(tick) is not int or tick <= previous:
            return None
        previous = tick
    if catalog[0]['tick'] != state['opened_at'] or catalog[-1]['tick'] != last_tick:
        return None
    replayed = burst.run(dict(credit=0, threshold=threshold, samples=catalog))['state']
    if (replayed['opened_at'], replayed['streak'], replayed['fired']) != (
            state['opened_at'], state['streak'], state['fired']):
        return None
    return len(catalog)


def _witness(ticks, threshold):
    samples = [dict(tick=tick, high=True) for tick in ticks]
    return dict(samples=samples, count=len(samples),
                probe_outcome='captured' if len(samples) >= threshold else 'waiting')


def _switch(db, device, state, revision, threshold):
    db.execute('UPDATE capture_devices SET revision=?, threshold=?, checkpoint=?,'
               ' pending_revision=NULL, pending_threshold=NULL WHERE name=?',
               (revision, threshold, json.dumps(state), device))
    return {'decision': 'switched', 'revision': revision, 'threshold': threshold}


def _revise(db, action, row, state):
    """Hand the selection rule to a new revision, mid-segment only when exact.

    An open, still-undecided segment may hide several high-count histories
    behind the truncated streak.  Switch immediately only when every history
    the device may still hold selects the same detail for the same future
    input — pinned down by a raw catalog, or equivalent on its own — and
    otherwise return two replayable witness histories that diverge.  With
    'defer' the new rule is parked and takes over when the active segment
    closes, leaving the old rule to finish the segment.
    """
    device = action['device']
    revision = action.get('revision')
    threshold = action.get('threshold')
    if not isinstance(revision, str) or type(threshold) is not int or threshold < 1:
        raise ValueError('invalid revision or threshold')
    if revision == row['revision']:
        return {'decision': 'revision_unchanged'}
    if state['opened_at'] is None or state['fired']:
        return _switch(db, device, state, revision, threshold)
    if action.get('defer'):
        db.execute('UPDATE capture_devices SET pending_revision=?, pending_threshold=? WHERE name=?',
                   (revision, threshold, device))
        return {'decision': 'deferred', 'revision': row['revision'], 'threshold': row['threshold'],
                'pending': dict(revision=revision, threshold=threshold)}
    count = _pin_count(action.get('catalog'), state, row['threshold'], row['last_tick'])
    pinned = count is not None
    if not pinned:
        lowest = state['streak']
        highest = row['last_tick'] - state['opened_at'] + 1
        if min(lowest, threshold) != min(highest, threshold):
            probe = dict(tick=row['last_tick'] + 1, high=True)
            minimal = [state['opened_at']] + list(range(row['last_tick'] - lowest + 2, row['last_tick'] + 1))
            return {'decision': 'ambiguous', 'probe': probe,
                    'witnesses': [_witness(minimal, threshold),
                                  _witness(range(state['opened_at'], row['last_tick'] + 1), threshold)]}
        count = lowest
    state['streak'] = min(count, threshold)
    result = _switch(db, device, state, revision, threshold)
    result['segment'] = dict(opened_at=state['opened_at'], count=count if pinned else None,
                             streak=state['streak'])
    return result


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
            initial = dict(streak=0, opened_at=None, fired=False, remaining=0, captures={},
                           last_sample=None)
            db.execute('INSERT INTO capture_devices VALUES(?,?,?,-1,?,NULL,NULL)',
                       (device, action['revision'], action['threshold'], json.dumps(initial)))
            return {'decision': 'configured'}
        if row is None:
            return {'decision': 'unknown_device'}
        state = json.loads(row['checkpoint'])
        if op == 'checkpoint':
            return dict(state=state, revision=row['revision'], threshold=row['threshold'],
                        last_tick=row['last_tick'], pending=_pending(row))
        if op == 'enable':
            state['remaining'] = action['space']
            db.execute('UPDATE capture_devices SET checkpoint=? WHERE name=?', (json.dumps(state), device))
            return {'decision': 'recording_enabled'}
        if op == 'ack':
            if action['revision'] != row['revision']:
                return {'decision': 'stale_revision'}
            detail = capture.open_detail(db, device, action['handle'])
            if detail and detail['revision'] == action['revision'] and detail['sample'] == action['sample']:
                return {'decision': 'existing_detail'}
            return {'decision': 'unknown_detail'}
        if op == 'revise':
            return _revise(db, action, row, state)
        if op != 'receive':
            raise ValueError('unknown device operation')
        sample = action['sample']
        if sample['tick'] <= row['last_tick']:
            return {'decision': 'stale_tick'}
        decision = burst.advance(state, sample, row['threshold'])
        result = {'decision': decision}
        revision, threshold = row['revision'], row['threshold']
        pending = _pending(row)
        if decision == 'captured':
            result['handle'] = capture.persist_detail(db, device, revision, state['opened_at'], sample)
        if decision == 'episode_closed' and pending is not None:
            result['activated'] = pending
            revision, threshold = pending['revision'], pending['threshold']
            pending = None
        state['last_sample'] = dict(sample)
        db.execute('UPDATE capture_devices SET revision=?, threshold=?, checkpoint=?, last_tick=?,'
                   ' pending_revision=?, pending_threshold=? WHERE name=?',
                   (revision, threshold, json.dumps(state), sample['tick'],
                    pending['revision'] if pending else None,
                    pending['threshold'] if pending else None, device))
        return result
