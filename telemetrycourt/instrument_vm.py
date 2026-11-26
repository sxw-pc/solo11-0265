"""Evaluate synthetic small-register probe instructions without external execution."""
LOW, HIGH = -7, 7


def execute(program, inputs):
    stack = []
    trace = []
    for instruction in program:
        kind = instruction['op']
        if kind == 'input':
            value = inputs[instruction['name']]
            if type(value) is not int or not LOW <= value <= HIGH:
                raise ValueError('input outside register range')
            stack.append(value)
            continue
        if kind not in ('add', 'subtract') or len(stack) < 2:
            raise ValueError('invalid probe instruction')
        right = stack.pop()
        left = stack.pop()
        actual = left + right if kind == 'add' else left - right
        value = min(HIGH, max(LOW, actual))
        stack.append(value)
        trace.append({'op': kind, 'stored': value, 'clipped': value != actual})
    if len(stack) != 1:
        raise ValueError('program must leave one value')
    return {'value': stack[0], 'trace': trace}
