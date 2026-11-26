"""Run a deterministic, discrete-time service queue for offline capacity exercises."""
from collections import deque


def nonnegative_integer(value):
    return type(value) is int and value >= 0


class ServiceQueue:
    def __init__(self, service_per_replica):
        if not nonnegative_integer(service_per_replica) or service_per_replica == 0:
            raise ValueError('service_per_replica must be a positive integer')
        self.service_per_replica = service_per_replica
        self.pending = deque()
        self.tick = 0
        self.next_request = 0

    def advance(self, arrivals, replicas):
        if not nonnegative_integer(arrivals) or not nonnegative_integer(replicas):
            raise ValueError('arrivals and replicas must be nonnegative integers')
        for _ in range(arrivals):
            self.pending.append((self.next_request, self.tick))
            self.next_request += 1
        completed = []
        capacity = replicas * self.service_per_replica
        for _ in range(min(capacity, len(self.pending))):
            request, entered = self.pending.popleft()
            completed.append({'request': request, 'entered': entered,
                              'completed': self.tick, 'wait': self.tick - entered})
        observation = {'tick': self.tick, 'arrivals': arrivals, 'replicas': replicas,
                       'backlog': len(self.pending), 'completed': completed}
        self.tick += 1
        return observation


def run(fixture):
    queue = ServiceQueue(fixture['service_per_replica'])
    samples = [queue.advance(arrivals, fixture['replicas']) for arrivals in fixture['arrivals']]
    return {'samples': samples, 'unfinished': len(queue.pending)}
