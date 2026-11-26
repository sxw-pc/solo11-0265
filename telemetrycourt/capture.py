"""A local, finite-credit detailed capture recorder for synthetic samples."""


def take(state, ticket, sample):
    """Commit the supplied sample under a previously unused capture ticket."""
    prior = state['captures'].get(ticket)
    if prior is not None:
        return 'already_captured' if prior == sample else 'ticket_conflict'
    if state['remaining'] == 0:
        return 'out_of_credit'
    state['captures'][ticket] = dict(sample)
    state['remaining'] -= 1
    return 'captured'


SCHEMA = """CREATE TABLE IF NOT EXISTS device_details (
    device TEXT NOT NULL, handle TEXT NOT NULL, episode INTEGER NOT NULL,
    revision TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(device,handle));"""


def persist_detail(db, device, revision, episode, sample):
    import json

    handle = f'{episode}/{revision}'
    db.execute('INSERT INTO device_details VALUES(?,?,?,?,?)',
               (device, handle, episode, revision, json.dumps(sample, sort_keys=True)))
    return handle


def open_detail(db, device, handle):
    import json

    from .store import one

    result = one(db, 'SELECT episode, revision, payload FROM device_details WHERE device=? AND handle=?',
                 (device, handle))
    if result is None:
        return None
    result['sample'] = json.loads(result.pop('payload'))
    return result
