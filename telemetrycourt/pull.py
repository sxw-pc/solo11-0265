"""Apply and receipt offline meter pulls using the baseline single-reader contract."""
import json

from . import meters
from .store import one, tx

SCHEMA = """CREATE TABLE IF NOT EXISTS meter_receipts(
    id TEXT PRIMARY KEY, request TEXT NOT NULL, response TEXT NOT NULL);"""


def run(db, fixture):
    db.executescript(meters.SCHEMA + SCHEMA)
    output = []
    for command in fixture:
        with tx(db):
            output.append(apply(db, command))
    return output


def apply(db, command):
    request = json.dumps(command, sort_keys=True, separators=(',', ':'))
    prior = one(db, 'SELECT request,response FROM meter_receipts WHERE id=?', (command['id'],))
    if prior:
        if prior['request'] == request:
            return json.loads(prior['response'])
        return {'decision': 'pull_identity_conflict'}
    meter = command['meter']
    if command['op'] == 'credit':
        meters.credit(db, meter, command['amount'])
        result = {'decision': 'credited', 'pending': meters.balance(db, meter)}
    elif command['op'] == 'pull':
        result = {'decision': 'drained', 'meter': meter, 'amount': meters.drain(db, meter)}
    else:
        raise ValueError('unknown meter operation')
    db.execute('INSERT INTO meter_receipts VALUES(?,?,?)',
               (command['id'], request, json.dumps(result, sort_keys=True)))
    return result
