"""Compile an empirical histogram from archived sample identity and synthetic values."""
from bisect import bisect_left
from . import archive


def run(db,fixture):
    summary=archive.run(db,fixture['query'])
    if summary['decision']!='rollup_ready':
        return summary
    edges=fixture['edges']
    if len(edges)<1 or sorted(set(edges))!=edges:
        return {'decision':'invalid_edges'}
    measurements=fixture['values']
    buckets=[]
    for time_bucket in summary['buckets']:
        counts=[0]*(len(edges)+1)
        missing=[]
        for sample in time_bucket['sample_ids']:
            if sample not in measurements:
                missing.append(sample)
                continue
            counts[bisect_left(edges,measurements[sample])]+=1
        buckets.append({'start':time_bucket['start'],'end':time_bucket['end'],'counts':counts,'missing':missing})
    return {'decision':'histogram_ready','uid':summary['uid'],'upper_bounds':edges,'buckets':buckets}
