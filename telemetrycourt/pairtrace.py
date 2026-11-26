"""Pair matching for a small, offline collector latency trial."""


def ordered_signs(pairs):
    signs = []
    for position, pair in enumerate(pairs, 1):
        if pair['position'] != position:
            raise ValueError('paired observations must be the committed prefix')
        baseline, candidate = pair['base_ms'], pair['candidate_ms']
        if any(type(value) is not int or value < 0 for value in (baseline, candidate)):
            raise ValueError('latency must be a nonnegative integer')
        if baseline == candidate:
            raise ValueError('seed trial requires untied pairs')
        signs.append(int(candidate < baseline))
    return signs
