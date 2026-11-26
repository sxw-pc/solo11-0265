"""Read the concrete synthetic source line identified by an exact sampled address."""
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
