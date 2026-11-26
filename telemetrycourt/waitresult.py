"""Issue a local completed or late result from actual request replay."""
from .waittrace import replay


def run(fixture):
    timeline = replay(fixture['tasks'])
    completion = timeline[fixture['target']]['finish']
    return dict(timeline=timeline, completion=completion,
                decision='on_time' if completion <= fixture['deadline'] else 'late')
