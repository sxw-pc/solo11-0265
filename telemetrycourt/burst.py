"""An offline threshold device that buys one detailed sample per high episode."""
from .capture import take


def advance(state, sample, threshold):
    if not sample['high']:
        state['streak'] = 0
        state['opened_at'] = None
        state['fired'] = False
        return 'episode_closed'
    if state['opened_at'] is None:
        state['opened_at'] = sample['tick']
    state['streak'] = min(threshold, state['streak'] + 1)
    if state['fired'] or state['streak'] < threshold:
        return 'waiting'
    ticket = str(state['opened_at'])
    result = take(state, ticket, sample)
    if result in ('captured', 'already_captured'):
        state['fired'] = True
    return result


def run(fixture):
    credit = fixture['credit']
    threshold = fixture['threshold']
    if type(credit) is not int or credit < 0 or type(threshold) is not int or threshold < 1:
        raise ValueError('invalid credit or threshold')
    state = dict(streak=0, opened_at=None, fired=False, remaining=credit, captures={})
    outcomes = []
    previous = -1
    for sample in fixture['samples']:
        tick = sample['tick']
        if type(tick) is not int or tick <= previous or type(sample['high']) is not bool:
            raise ValueError('ticks must increase and high must be boolean')
        outcomes.append(advance(state, sample, threshold))
        previous = tick
    return dict(state=state, outcomes=outcomes)
