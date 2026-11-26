"""Build a frozen rollup from the current telemetry evidence."""
from collections import defaultdict
from .store import allrows,one


def facts(db, object_name, signal, start, end):
    return allrows(db,"""SELECT s.id,s.corrected_at,l.object_uid,s.source FROM samples s
        JOIN leases l ON l.id=s.lease JOIN topologies t ON t.object=s.object AND t.uid=l.object_uid
        WHERE s.object=? AND s.signal=? AND s.status='trusted' AND l.status='active'
          AND s.corrected_at>=? AND s.corrected_at<? ORDER BY s.corrected_at,s.id""",
        (object_name,signal,start,end))


def run(db, fixture):
    start,end,width=(fixture[key] for key in ('start','end','bucket_width'))
    if width<=0 or start>=end:
        return {'decision':'invalid_rollup_window'}
    top=one(db,'SELECT uid FROM topologies WHERE object=?',(fixture['object'],))
    if top is None:
        return {'decision':'object_missing'}
    buckets=defaultdict(list)
    for sample in facts(db,fixture['object'],fixture['signal'],start,end):
        left=start+(sample['corrected_at']-start)//width*width
        buckets[left].append(sample['id'])
    return {'decision':'rollup_ready','uid':top['uid'],'buckets':[
        {'start':left,'end':min(left+width,end),'count':len(ids),'sample_ids':ids}
        for left,ids in sorted(buckets.items())]}
