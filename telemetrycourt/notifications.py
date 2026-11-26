"""Create offline notifications from the latest alert labels."""
from .store import one


def alert_label(db, identity):
    return one(db,"""SELECT c.object_uid,l.label,l.at
        FROM alert_labels l JOIN blind_cases c ON c.id=l.case_id
        WHERE c.id=? AND l.alert=? ORDER BY l.at DESC,l.id DESC LIMIT 1""",
        (identity['case'],identity['alert']))


def run(db, fixture):
    remaining = dict(fixture['routes'])
    pages = []
    skipped = []
    for entry in fixture['alerts']:
        label = alert_label(db,entry)
        target = entry['route']
        if label is None:
            reason = 'label_missing'
        elif label['label']!='signal_insufficient':
            reason = 'no_active_blind_alert'
        elif remaining.get(target,0)<=0:
            reason = 'route_exhausted'
        else:
            remaining[target] -= 1
            pages.append({**entry,'object_uid':label['object_uid'],'observed_at':label['at']})
            continue
        skipped.append({'alert':entry['alert'],'reason':reason})
    return {'pages':pages,'skipped':skipped,'remaining':remaining}
