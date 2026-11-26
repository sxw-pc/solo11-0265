"""Resolve an offline sample transport frame against acknowledged receive state."""


def identity(frame):
    return tuple(frame[k] for k in ('sample','generation','value'))


def resolve(frame, acknowledgement, accepted):
    if frame['encoding']=='full':
        return {'wire':frame['value'],'decoded':frame['value']}
    if frame['encoding']!='delta':
        return None
    key=tuple(frame['base'])
    if key not in acknowledgement and key not in accepted:
        return None
    if key[1]!=frame['generation']:
        return None
    return {'wire':frame['value']-key[2],'decoded':frame['value'],'base':list(key)}
