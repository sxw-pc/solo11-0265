"""Turn the first applicable synthetic log rule into a local review work item."""
from . import emitlog
from .store import one, tx

SCHEMA = """CREATE TABLE IF NOT EXISTS log_review_work(
    session TEXT NOT NULL, sequence INTEGER NOT NULL, action TEXT NOT NULL,
    PRIMARY KEY(session, sequence));"""


def choose(rules, parsed):
    for rule in rules:
        if all(parsed.get(key) == value for key, value in rule['where'].items()):
            return rule['action']
    return 'none'


def active(db, session):
    return dict(db.execute('SELECT sequence,action FROM log_review_work WHERE session=? ORDER BY sequence',
                           (session,)).fetchall())


def run(db, fixture):
    db.executescript(SCHEMA)
    results = []
    with tx(db):
        for row in fixture['rows']:
            parsed = emitlog.parse(row)
            identity = parsed['session'], parsed['sequence']
            action = choose(fixture['rules'], parsed)
            prior = one(db, 'SELECT action FROM log_review_work WHERE session=? AND sequence=?', identity)
            if prior is not None and prior['action'] != action:
                results.append('action_conflict')
                continue
            if prior is None and action != 'none':
                db.execute('INSERT INTO log_review_work VALUES(?,?,?)', (*identity, action))
            results.append(action)
    return results
