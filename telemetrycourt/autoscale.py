"""Treat an offline FIFO observation as the input to a baseline replica controller."""
from .loadlab import ServiceQueue, nonnegative_integer


def next_replicas(backlog, current, floor, ceiling, target):
    if backlog > target:
        return min(current + 1, ceiling)
    if backlog == 0:
        return max(current - 1, floor)
    return current


def run(fixture):
    minimum, maximum, target = (fixture[key] for key in ('min_replicas', 'max_replicas', 'backlog_target'))
    current = fixture.get('initial_replicas', minimum)
    if not all(map(nonnegative_integer, (minimum, maximum, target, current))) or not minimum <= current <= maximum:
        raise ValueError('invalid replica limits or target')
    lab = ServiceQueue(fixture['service_per_replica'])
    samples = []
    for arrivals in fixture['arrivals']:
        sample = lab.advance(arrivals, current)
        current = next_replicas(sample['backlog'], current, minimum, maximum, target)
        samples.append({**sample, 'next_replicas': current})
    return {'samples': samples, 'unfinished': len(lab.pending), 'next_replicas': current}
