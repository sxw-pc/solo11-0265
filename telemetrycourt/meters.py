"""Keep synthetic service-meter increments available to an offline collector."""
from .store import one

SCHEMA = """CREATE TABLE IF NOT EXISTS meter_totals(
    meter TEXT PRIMARY KEY, pending INTEGER NOT NULL CHECK (pending >= 0));"""


def credit(db, meter, amount):
    if not meter or type(amount) is not int or amount < 0:
        raise ValueError('meter and nonnegative integer amount required')
    db.execute('INSERT INTO meter_totals VALUES(?,?) '
               'ON CONFLICT(meter) DO UPDATE SET pending=pending+excluded.pending',
               (meter, amount))


def balance(db, meter):
    row = one(db, 'SELECT pending FROM meter_totals WHERE meter=?', (meter,))
    return row['pending'] if row else 0


def drain(db, meter):
    amount = balance(db, meter)
    db.execute('UPDATE meter_totals SET pending=0 WHERE meter=?', (meter,))
    return amount
