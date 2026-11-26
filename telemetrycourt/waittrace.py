"""Calculate synthetic work completion from a measured worker and data sequence."""


def replay(tasks):
    results = {}
    occupied_until = {}
    for item in tasks:
        worker = item['worker']
        input_ready = max((results[parent]['finish'] for parent in item['depends']), default=0)
        worker_ready = occupied_until.get(worker, 0)
        start = max(item['arrival'], input_ready, worker_ready)
        finish = start + item['work']
        results[item['id']] = {'start': start, 'finish': finish, 'worker': worker}
        occupied_until[worker] = finish
    return results
