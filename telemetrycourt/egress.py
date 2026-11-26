"""Reserve rolling offline export credit and obtain actual spool reservations."""
from . import spool
from .store import one,tx

SCHEMA="""CREATE TABLE IF NOT EXISTS export_credits(
    delivery TEXT PRIMARY KEY, tenant TEXT NOT NULL, logical_at INTEGER NOT NULL,
    used INTEGER NOT NULL);"""


def run(db, fixture):
    db.executescript(SCHEMA)
    tenant=fixture['tenant']
    delivery=fixture['delivery']
    time=fixture['at']
    with tx(db):
        prior=one(db,'SELECT * FROM export_credits WHERE delivery=?',(delivery,))
        if prior:
            if prior['tenant']!=tenant:
                return {'decision':'reservation_identity_conflict'}
            return {'decision':'already_reserved','used':prior['used']}
        period=fixture['window']
        budget=fixture['quota']
        if period<=0 or budget<0:
            return {'decision':'invalid_quota'}
        used=one(db,'SELECT COALESCE(sum(used),0) AS n FROM export_credits WHERE tenant=? AND logical_at>? AND logical_at<=?',
            (tenant,time-period,time))['n']
        remaining=max(0,budget-used)
        plan=spool.run(db,{**fixture['pack'],'bytes':remaining})
        count=remaining-plan['remaining_bytes']
        db.execute('INSERT INTO export_credits VALUES(?,?,?,?)',(delivery,tenant,time,count))
        return {'decision':'reserved','used':count,'plan':plan}
