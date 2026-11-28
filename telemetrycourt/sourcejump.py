"""Read the concrete synthetic source line identified by an exact sampled address.

The single-instant entry points (``historical``/``repair``) assume the sampler
clock and the host load log share one exact instant.  The batch entry points
(``navigate_batch``/``navigate_repair``) handle a recovered batch whose sampler
lost its host-clock offset: every frame in one batch must be explained by the
same physically reachable clock interpretation, and contradictory evidence
rejects the whole batch instead of mixing per-frame plausible answers.
"""
from . import imageload


def open_line(documents, location):
    document = documents.get(location['document'])
    line = location['line']
    if document is None or not 1 <= line <= len(document):
        return None
    return dict(location, text=document[line - 1])


def historical(fixture, at, pc):
    loaded = imageload.locate(fixture['images'], at, pc)
    if loaded is None:
        return {'decision': 'unmapped_address'}
    build, offset = loaded
    sites = fixture['symbols'].get(build, {}).get(str(offset))
    if not sites:
        return {'decision': 'unmapped_symbol'}
    stack = [open_line(fixture['documents'], site) for site in sites]
    if any(site is None for site in stack):
        return {'decision': 'source_unavailable'}
    return {'decision': 'historical_source', 'build': build, 'stack': stack}


def repair(fixture, origin):
    target = fixture['replacements'].get(origin)
    return open_line(fixture['documents'], target) if target is not None else None


def run(fixture):
    return [historical(fixture, row['at'], row['pc']) for row in fixture['samples']]


def _clock_offsets(fixture):
    """Candidate host-clock shifts for one sampler batch (synthetic ledger)."""
    return list(fixture.get('clock_offsets', (0,)))


def _frame_at(fixture, at, pc):
    """Locate the unique loaded build for one frame under one clock shift."""
    loaded = imageload.locate(fixture['images'], at, pc)
    if loaded is None:
        return None
    build, offset = loaded
    return {'build': build, 'offset': offset}


def _frame_evidence(fixture, frame):
    """Archive reading for one still-compatible frame interpretation."""
    sites = fixture['symbols'].get(frame['build'], {}).get(str(frame['offset']))
    if not sites:
        # A missing debug symbol is not evidence that the build never loaded.
        return dict(frame, decision='unmapped_symbol')
    stack = [open_line(fixture['documents'], site) for site in sites]
    if any(site is None for site in stack):
        return dict(frame, decision='source_unavailable')
    return dict(frame, decision='historical_source', stack=stack)


def navigate_batch(fixture, batch):
    """Resolve a whole recovered batch under one shared clock interpretation.

    Each candidate offset is falsified only by the real load table (no image
    covers the frame at that host time).  Missing symbols or archived source
    cannot falsify a load.  When no offset survives, the batch is rejected as a
    unit so frames from incompatible explanations are never stitched together.
    """
    at = batch['at']
    rejected, viable = [], []
    for shift in _clock_offsets(fixture):
        host_at = at + shift
        interpretations = []
        falsified = None
        for pc in batch['frames']:
            frame = _frame_at(fixture, host_at, pc)
            if frame is None:
                falsified = pc
                break
            interpretations.append(frame)
        if falsified is not None:
            rejected.append({'offset': shift, 'host_at': host_at,
                             'frame': falsified, 'reason': 'unmapped_address'})
        else:
            viable.append({'offset': shift, 'host_at': host_at,
                           'frames': interpretations})
    if not viable:
        return {'decision': 'batch_clock_rejected', 'batch': batch['id'],
                'sampled_at': at, 'rejected': rejected}
    frames = []
    for index, pc in enumerate(batch['frames']):
        candidates = [_frame_evidence(fixture, choice['frames'][index])
                      for choice in viable]
        if len(viable) == 1:
            frames.append(dict({'address': pc}, **candidates[0]))
            continue
        # Cross-build uncertainty is distinct evidence from a missing symbol.
        frames.append({'address': pc, 'decision': 'ambiguous',
                       'interpretations': candidates})
    return {'decision': 'batch_navigated', 'batch': batch['id'],
            'sampled_at': at, 'offsets': [c['offset'] for c in viable],
            'frames': frames}


def _trace_lineage(fixture, origin):
    """Walk an authorised position lineage, verifying every hop's real text.

    Returns the open current-workspace cursor plus the full position history,
    or ``None`` when a hop was revoked, split or points at content that is not
    actually present.  Each hop names the exact source position and version.
    """
    hops = fixture.get('lineages', {}).get(origin)
    if not hops:
        return None
    history = []
    for hop in hops:
        opened = open_line(fixture['documents'], hop)
        if opened is None:
            return None
        history.append(dict(opened, version=hop['version']))
    target = history[-1]
    return {'origin': origin, 'target': {k: target[k] for k in ('document', 'line', 'text')},
            'history': history}


def _compatible_origins(fixture, frame):
    """Origins of every still-compatible real provenance for one frame."""
    if frame['decision'] == 'historical_source':
        return [site['origin'] for site in frame['stack']]
    if frame['decision'] == 'ambiguous':
        origins = []
        for interpretation in frame['interpretations']:
            if interpretation['decision'] == 'historical_source':
                origins.extend(site['origin'] for site in interpretation['stack'])
        return origins
    return []


def navigate_repair(fixture, frame):
    """Issue an editable repair cursor only when every compatible provenance.

    reaches the same current workspace location through a verifiable position
    lineage.  Revoked mappings, split destinations or one missing chain cannot
    be substituted by another chain that happens to work.
    """
    origins = _compatible_origins(fixture, frame)
    if not origins:
        return {'decision': 'repair_symbol_unavailable',
                'address': frame['address']}
    traces = []
    for origin in origins:
        trace = _trace_lineage(fixture, origin)
        if trace is None:
            return {'decision': 'repair_lineage_missing',
                    'address': frame['address'], 'origin': origin}
        traces.append(trace)
    destinations = {(t['target']['document'], t['target']['line'])
                    for t in traces}
    if len(destinations) != 1:
        return {'decision': 'repair_split', 'address': frame['address'],
                'destinations': [{'document': doc, 'line': line}
                                 for doc, line in sorted(destinations)]}
    chosen = traces[0]
    return {'decision': 'repair_cursor', 'address': frame['address'],
            'cursor': chosen['target'], 'provenance': traces}
