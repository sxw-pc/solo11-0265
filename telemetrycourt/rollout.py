"""One terminal decision for switching an offline telemetry collector route."""
from fractions import Fraction
from math import comb

from . import pairtrace
from .store import one, tx

SCHEMA = """CREATE TABLE IF NOT EXISTS collector_routes (
    route TEXT PRIMARY KEY, collector TEXT NOT NULL);"""


def fair_tail(observations, wins):
    return Fraction(sum(comb(observations, n) for n in range(wins, observations + 1)), 2 ** observations)


def active(db, route):
    row = one(db, 'SELECT collector FROM collector_routes WHERE route=?', (route,))
    return row['collector'] if row else 'baseline'


def run(db, fixture):
    db.executescript(SCHEMA)
    signs = pairtrace.ordered_signs(fixture['pairs'])
    planned = fixture['planned']
    if type(planned) is not int or planned < 1 or len(signs) > planned:
        raise ValueError('invalid trial horizon')
    route = fixture['route']
    alpha = Fraction(fixture['false_release_limit'])
    if not 0 < alpha < 1:
        raise ValueError('invalid risk bound')
    decision = 'collect_more'
    tail = None
    with tx(db):
        if len(signs) == planned:
            tail = fair_tail(len(signs), sum(signs))
            if tail <= alpha:
                db.execute('INSERT INTO collector_routes VALUES(?,?) ON CONFLICT(route) '
                           'DO UPDATE SET collector=excluded.collector', (route, fixture['candidate']))
                decision = 'released'
            else:
                decision = 'hold'
        return {'decision': decision, 'risk': str(tail) if tail is not None else None,
                'pairs': len(signs), 'next_collector': active(db, route)}
