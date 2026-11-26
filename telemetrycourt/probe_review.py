"""Produce the real local diagnostic decision from register execution."""
from .instrument_vm import execute


def run(fixture):
    result = execute(fixture['program'], fixture['inputs'])
    return {**result, 'decision': 'open_review' if result['value'] >= fixture['limit'] else 'normal'}
