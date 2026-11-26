"""Pair sequential timing stages of offline synthetic requests."""
from collections import Counter


def numbered(stage):
    durations = {}
    for row in stage:
        request = row['request']
        duration = row['duration']
        if request in durations or type(duration) is not int or duration < 0:
            raise ValueError('invalid or duplicate request timing')
        durations[request] = duration
    return durations


def pair(front, back):
    left = numbered(front)
    right = numbered(back)
    if left.keys() != right.keys():
        raise ValueError('missing paired timing')
    return {request: left[request] + right[request] for request in left}


def marginal(stage):
    return dict(sorted(Counter(numbered(stage).values()).items()))
