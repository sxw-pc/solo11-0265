"""A local, finite-credit detailed capture recorder for synthetic samples."""


def take(state, ticket, sample):
    """Commit the supplied sample under a previously unused capture ticket."""
    prior = state['captures'].get(ticket)
    if prior is not None:
        return 'already_captured' if prior == sample else 'ticket_conflict'
    if state['remaining'] == 0:
        return 'out_of_credit'
    state['captures'][ticket] = dict(sample)
    state['remaining'] -= 1
    return 'captured'
