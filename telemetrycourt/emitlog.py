"""Read synthetic structured log rows and form an intentionally coarser view."""


def parse(row):
    schema = row['schema']
    if schema not in ('rich', 'compact'):
        raise ValueError('unknown log schema')
    common = {name: row[name] for name in ('session', 'sequence', 'family')}
    if schema == 'rich':
        common['phase'] = row['phase']
    return common


def compact(row):
    parsed = parse(row)
    parsed.pop('phase', None)
    return dict(parsed, schema='compact')
