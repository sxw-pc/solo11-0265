"""Publish a synthetic service statement from exact paired request timings."""
from .stage_times import pair
from .store import one, tx

SCHEMA = """CREATE TABLE IF NOT EXISTS latency_statements (
    statement TEXT PRIMARY KEY, late INTEGER NOT NULL, status TEXT NOT NULL);"""


def published(db, identity):
    return one(db, 'SELECT late,status FROM latency_statements WHERE statement=?', (identity,))


def run(db, fixture):
    db.executescript(SCHEMA)
    totals = pair(fixture['front'], fixture['back'])
    late = sum(duration > fixture['deadline'] for duration in totals.values())
    status = 'within_contract' if late <= fixture['allowed_late'] else 'outside_contract'
    identity = fixture['statement']
    with tx(db):
        prior = published(db, identity)
        outcome = dict(late=late, status=status)
        if prior is None:
            db.execute('INSERT INTO latency_statements VALUES(?,?,?)', (identity, late, status))
        elif prior != outcome:
            return {'status': 'statement_conflict'}
    return outcome
