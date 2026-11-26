"""Build a local export manifest from trusted samples and a fixed byte budget."""
from .store import one
from . import frames


def trusted_sample(db, identity):
    return one(db,"""SELECT s.id,s.source,s.signal,s.sequence,s.corrected_at,l.object_uid
        FROM samples s JOIN leases l ON s.lease=l.id
        JOIN topologies t ON t.object=s.object AND t.uid=l.object_uid
        WHERE s.id=? AND s.status='trusted' AND l.status='active'""",(identity,))


def run(db, fixture):
    """Spool sample references in arrival order and never overbook an export."""
    remaining = fixture['bytes']
    planned = []
    deferred = []
    seen = set()
    accepted_frames=set()
    acknowledged={tuple(base) for base in fixture.get('acknowledged',[])}
    for packet in fixture['packets']:
        sample = trusted_sample(db,packet['sample'])
        byte_size = packet['bytes']
        frame=packet.get('frame')
        encoding=frames.resolve(frame,acknowledged,accepted_frames) if frame is not None else None
        if sample is None:
            reason = 'sample_unavailable'
        elif frame is not None and frame['sample']!=sample['id']:
            reason = 'frame_identity_mismatch'
        elif sample['id'] in seen:
            reason = 'already_planned'
        elif not isinstance(byte_size,int) or byte_size <= 0:
            reason = 'invalid_bytes'
        elif frame is not None and encoding is None:
            reason = 'frame_base_unavailable'
        elif byte_size > remaining:
            reason = 'budget_exhausted'
        else:
            remaining -= byte_size
            seen.add(sample['id'])
            item={**sample,'bytes':byte_size}
            if frame is not None:
                item['encoding']=encoding
                accepted_frames.add(frames.identity(frame))
            planned.append(item)
            continue
        deferred.append({'sample':packet['sample'],'reason':reason})
    return {'planned':planned,'deferred':deferred,'remaining_bytes':remaining}
