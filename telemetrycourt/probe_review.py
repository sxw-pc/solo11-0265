"""Produce the real local diagnostic decision from register execution.

Two entry layers share the same small-register machine:

* ``run`` replays a legacy fixture (program + inputs + limit) and keeps the
  original review semantics.
* ``issue`` orchestrates a fixed program for a numeric contract and accepts it
  only by replaying it through :mod:`telemetrycourt.instrument_vm` over the
  whole legal reading domain.  Raw exact contracts forbid every saturation;
  legacy contracts may only saturate at their named clip points.
* ``run_certified`` executes a signed certificate against one reading.
  Readings outside the signed relation domain are held for review and never
  mixed with the certificate's threshold into a fresh review decision.
"""
import re
from itertools import permutations, product

from .instrument_vm import execute, LOW, HIGH

_RELATIONS = {
    '>=': lambda a, b: a >= b,
    '<=': lambda a, b: a <= b,
    '>': lambda a, b: a > b,
    '<': lambda a, b: a < b,
    '==': lambda a, b: a == b,
    '!=': lambda a, b: a != b,
}
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')
MAX_INPUTS = 5
MAX_NAMED_CLIPS = 2


# ---------------------------------------------------------------------------
# Expression parsing (signed input terms only; no constants, no repetition)
# ---------------------------------------------------------------------------
def parse_expression(text):
    """Parse ``a+b-c`` into ``[(1, 'a'), (1, 'b'), (-1, 'c')]``."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError('expression must be a non-empty string')
    source = text.strip()
    terms = []
    index = 0
    sign = 1
    expecting_sign = True
    while index < len(source):
        char = source[index]
        if char.isspace():
            index += 1
            continue
        if expecting_sign:
            if char == '+':
                sign = 1
            elif char == '-':
                sign = -1
            elif not terms:
                sign = 1
                expecting_sign = False
                continue
            else:
                raise ValueError('terms must be joined by + or -')
            index += 1
            expecting_sign = False
            continue
        match = _NAME.match(source, index)
        if not match:
            raise ValueError('expression may only combine named inputs with + or -')
        name = match.group(0)
        if any(existing == name for _, existing in terms):
            raise ValueError('each input may appear only once in an expression')
        terms.append((sign, name))
        index = match.end()
        sign = 1
        expecting_sign = True
    if not terms or not expecting_sign:
        raise ValueError('malformed expression')
    return terms


def _coefficient_vector(terms):
    vector = {}
    for sign, name in terms:
        vector[name] = vector.get(name, 0) + sign
    return {name: coeff for name, coeff in vector.items() if coeff}


# ---------------------------------------------------------------------------
# Legal reading domains: small integer bounds, relations, non-mixing groups
# ---------------------------------------------------------------------------
def _normalized_domain(doc):
    """Return ``[(bounds, relations), ...]`` from a contract or certificate."""
    if 'groups' in doc and doc['groups'] is not None:
        raw_groups = doc['groups']
    elif 'domain' in doc and doc['domain'] is not None:
        raw_groups = doc['domain']['groups']
    else:
        raw_groups = [{'inputs': doc.get('inputs') or doc.get('bounds'),
                       'relations': doc.get('relations', [])}]
    groups = []
    for group in raw_groups:
        raw_bounds = group.get('inputs') or group.get('bounds')
        if not raw_bounds:
            raise ValueError('each domain group must bound every input')
        bounds = {}
        for name, bound in raw_bounds.items():
            if len(bound) != 2 or any(type(v) is not int for v in bound):
                raise ValueError('input bounds must be integer [low, high] pairs')
            low, high = bound
            if not (LOW <= low <= high <= HIGH):
                raise ValueError('input bounds outside the register range')
            bounds[name] = (low, high)
        relations = tuple(group.get('relations', ()))
        for relation in relations:
            if relation['op'] not in _RELATIONS:
                raise ValueError('unsupported relation operator')
        groups.append((bounds, relations))
    if not groups:
        raise ValueError('the legal domain must contain at least one group')
    return groups


def _relation_holds(reading, relation):
    right = reading[relation['right']] if isinstance(relation['right'], str) else relation['right']
    if type(right) is not int:
        raise ValueError('relation bounds must be named inputs or integers')
    return _RELATIONS[relation['op']](reading[relation['left']], right)


def _group_points(bounds, relations):
    names = sorted(bounds)
    ranges = [range(bounds[name][0], bounds[name][1] + 1) for name in names]
    for combo in product(*ranges):
        reading = dict(zip(names, combo))
        if all(_relation_holds(reading, relation) for relation in relations):
            yield reading


def domain_points(domain):
    """All legal readings; groups are unioned, never cross-multiplied."""
    seen = set()
    points = []
    for bounds, relations in domain:
        for reading in _group_points(bounds, relations):
            key = tuple(sorted(reading.items()))
            if key not in seen:
                seen.add(key)
                points.append(reading)
    return points


def domain_contains(domain, reading):
    for bounds, relations in domain:
        if set(reading) != set(bounds):
            continue
        if any(not (LOW <= value <= HIGH) for value in reading.values()):
            return False
        if any(not (bounds[name][0] <= reading[name] <= bounds[name][1]) for name in bounds):
            continue
        if all(_relation_holds(reading, relation) for relation in relations):
            return True
    return False


def _independent_box(domain):
    names = sorted({name for bounds, _ in domain for name in bounds})
    return {name: (min(bounds[name][0] for bounds, _ in domain if name in bounds),
                   max(bounds[name][1] for bounds, _ in domain if name in bounds))
            for name in names}


# ---------------------------------------------------------------------------
# Fixed-program enumeration over the original input/add/subtract primitives
# ---------------------------------------------------------------------------
def _labeled_trees(leaves):
    if len(leaves) == 1:
        yield leaves[0]
        return
    for split in range(1, len(leaves)):
        for left in _labeled_trees(leaves[:split]):
            for right in _labeled_trees(leaves[split:]):
                for op in ('add', 'subtract'):
                    yield ('op', op, left, right)


def _node_coefficients(node):
    if node[0] == 'in':
        return {node[1]: 1}
    _, op, left, right = node
    merged = dict(_node_coefficients(left))
    for name, coeff in _node_coefficients(right).items():
        merged[name] = merged.get(name, 0) + (coeff if op == 'add' else -coeff)
    return {name: coeff for name, coeff in merged.items() if coeff}


def _flatten(node, instructions, nodes):
    if node[0] == 'in':
        instructions.append({'op': 'input', 'name': node[1]})
        return
    _, op, left, right = node
    _flatten(left, instructions, nodes)
    _flatten(right, instructions, nodes)
    instructions.append({'op': op})
    nodes.append(node)


def candidate_programs(names, target_vector):
    """Every distinct fixed program whose root computes the target vector."""
    seen = set()
    programs = []
    for ordering in permutations(sorted(names)):
        leaves = tuple(('in', name) for name in ordering)
        for tree in _labeled_trees(leaves):
            if _node_coefficients(tree) != target_vector:
                continue
            instructions = []
            nodes = []
            _flatten(tree, instructions, nodes)
            key = tuple((step['op'], step.get('name')) for step in instructions)
            if key not in seen:
                seen.add(key)
                programs.append((instructions, nodes))
    return programs


def named_clip_steps(program_nodes, named_clips):
    """Map each named clip to the trace step that preserves its exact point.

    Returns ``None`` when a named clip cannot be represented by this program,
    i.e. reassociating across the authorized point would hide the business
    reading inside a different operation.
    """
    step_of_clip = {}
    for clip in named_clips:
        wanted = _coefficient_vector(parse_expression(clip['expression']))
        matches = [index for index, node in enumerate(program_nodes)
                   if node[1] == clip['op'] and _node_coefficients(node) == wanted]
        if not matches or len(set(matches) & set(step_of_clip.values())):
            return None
        step_of_clip[clip['name']] = matches[0]
    return step_of_clip


# ---------------------------------------------------------------------------
# Acceptance: every decision below comes from instrument_vm.execute replays
# ---------------------------------------------------------------------------
def _exact_target(reading, target_vector):
    return sum(coeff * reading[name] for name, coeff in target_vector.items())


def _replay(program, reading):
    return execute(program, reading)


def _evaluate_candidate(program, nodes, target_vector, domain, kind, named_clips):
    """Return evidence on success, or the first runnable failure otherwise."""
    authorized_clip_steps = set()
    clip_map = {}
    if kind == 'legacy_clip':
        clip_map = named_clip_steps(nodes, named_clips)
        if clip_map is None:
            return None, {'reason': 'named_clip_not_representable'}
        authorized_clip_steps = set(clip_map.values())

    stored_ranges = {}
    clipped_steps = set()
    for reading in domain_points(domain):
        replay = _replay(program, reading)
        exact = _exact_target(reading, target_vector)
        for step, row in enumerate(replay['trace']):
            stored = row['stored']
            if step not in stored_ranges:
                stored_ranges[step] = [stored, stored]
            else:
                stored_ranges[step][0] = min(stored_ranges[step][0], stored)
                stored_ranges[step][1] = max(stored_ranges[step][1], stored)
            if row['clipped']:
                clipped_steps.add(step)
                if kind == 'legacy_clip' and step not in authorized_clip_steps:
                    return None, {'reason': 'unauthorized_intermediate_saturation',
                                  'reading': reading, 'exact': exact, 'replay': replay}
            if kind == 'raw_exact' and row['clipped']:
                return None, {'reason': 'intermediate_saturation',
                              'reading': reading, 'exact': exact, 'replay': replay}
        if kind == 'raw_exact' and replay['value'] != exact:
            return None, {'reason': 'result_differs_from_exact_contract',
                          'reading': reading, 'exact': exact, 'replay': replay}

    evidence = {
        'node_coefficients': [_node_coefficients(node) for node in nodes],
        'stored_ranges': {str(step): bounds for step, bounds in stored_ranges.items()},
        'clipped_steps': sorted(clipped_steps),
        'named_clip_steps': clip_map,
    }
    return evidence, None


def _box_domain(domain):
    return [(_independent_box(domain), ())]


def _serializable_domain(domain):
    return {'groups': [{'bounds': {name: list(bound) for name, bound in bounds.items()},
                        'relations': list(relations)}
                       for bounds, relations in domain]}


def _validate_contract(contract):
    kind = contract.get('kind')
    if kind not in ('raw_exact', 'legacy_clip'):
        raise ValueError('contract kind must be raw_exact or legacy_clip')
    terms = parse_expression(contract['expression'])
    names = sorted({name for _, name in terms})
    if not names or len(names) > MAX_INPUTS:
        raise ValueError('a contract may use at most five inputs')
    domain = _normalized_domain(contract)
    bounded = {name for bounds, _ in domain for name in bounds}
    if bounded != set(names):
        raise ValueError('expression inputs and domain bounds must name the same readings')
    if not domain_points(domain):
        raise ValueError('the legal domain is empty')
    named_clips = tuple(contract.get('named_clips', ()))
    if kind == 'raw_exact' and named_clips:
        raise ValueError('raw exact contracts cannot reserve clip points')
    if kind == 'legacy_clip' and not named_clips:
        raise ValueError('legacy contracts must name the preserved clip points')
    if len(named_clips) > MAX_NAMED_CLIPS:
        raise ValueError('at most two named clip points are allowed')
    clip_names = set()
    for clip in named_clips:
        if clip['op'] not in ('add', 'subtract'):
            raise ValueError('named clips must be add or subtract readings')
        clip_terms = parse_expression(clip['expression'])
        clip_inputs = {name for _, name in clip_terms}
        if not clip_inputs <= set(names) or clip['name'] in clip_names:
            raise ValueError('named clip expression is out of contract scope')
        clip_names.add(clip['name'])
    if type(contract.get('limit')) is not int:
        raise ValueError('contract limit must be an integer')
    return terms, names, domain, named_clips


def issue(contract):
    """Orchestrate and accept a fixed program for the numeric contract."""
    terms, names, domain, named_clips = _validate_contract(contract)
    kind = contract['kind']
    target_vector = _coefficient_vector(terms)
    points = domain_points(domain)
    exact_values = [_exact_target(reading, target_vector) for reading in points]
    overflow = [{'reading': reading, 'exact': exact}
                for reading, exact in zip(points, exact_values)
                if not LOW <= exact <= HIGH]

    candidate_failures = []
    signed = None
    candidates = candidate_programs(names, target_vector)
    for program, nodes in candidates:
        evidence, failure = _evaluate_candidate(
            program, nodes, target_vector, domain, kind, named_clips)
        if failure is None:
            signed = (program, nodes, evidence)
            break
        candidate_failures.append({'program': program, 'failure': failure})

    box = _box_domain(domain)
    box_signable = any(
        _evaluate_candidate(program, nodes, target_vector, box, kind, named_clips)[1] is None
        for program, nodes in candidates)

    common = {
        'contract_id': contract['id'],
        'kind': kind,
        'expression': contract['expression'],
        'limit': contract['limit'],
        'register': [LOW, HIGH],
        'domain': _serializable_domain(domain),
        'independent_box': {'bounds': {name: list(bound)
                                       for name, bound in _independent_box(domain).items()},
                            'signable_without_relations': box_signable},
    }
    if signed is not None:
        program, nodes, evidence = signed
        certificate = {
            'status': 'signed',
            **common,
            'program': program,
            'proof': {
                'domain_points': len(points),
                'node_coefficients': evidence['node_coefficients'],
                'stored_ranges': evidence['stored_ranges'],
                'clipped_steps': evidence['clipped_steps'],
                'exact_target_range': [min(exact_values), max(exact_values)],
            },
            'named_clips': [
                {'name': clip['name'], 'expression': clip['expression'], 'op': clip['op'],
                 'step': evidence['named_clip_steps'][clip['name']]}
                for clip in named_clips],
        }
        return certificate

    first_group_witnesses = {}
    for record in candidate_failures:
        failure = record['failure']
        if 'reading' not in failure:
            continue
        first_node = _program_nodes(record['program'])[0]
        key = ''.join(sorted(_node_coefficients(first_node)))
        first_group_witnesses.setdefault(key, failure['reading'])
    return {
        'status': 'refused',
        **common,
        'reason': 'no_fixed_program_satisfies_contract',
        'unsigned_domain': points,
        'final_exact_range': [min(exact_values), max(exact_values)],
        'register_overflow': overflow,
        'first_group_witnesses': first_group_witnesses,
        'candidates': candidate_failures,
    }


def _program_nodes(program):
    symbolic_stack = []
    nodes = []
    for instruction in program:
        if instruction['op'] == 'input':
            symbolic_stack.append(('in', instruction['name']))
            continue
        right = symbolic_stack.pop()
        left = symbolic_stack.pop()
        node = ('op', instruction['op'], left, right)
        symbolic_stack.append(node)
        nodes.append(node)
    return nodes


def verify_artifact(artifact):
    """Re-run every embedded failure witness through the real VM."""
    checked = []
    for candidate in artifact.get('candidates', ()):
        failure = candidate['failure']
        if 'replay' not in failure:
            continue
        replay = _replay(candidate['program'], failure['reading'])
        if replay != failure['replay']:
            return False, checked
        checked.append({'program': candidate['program'], 'reading': failure['reading'],
                        'replay': replay})
    for record in artifact.get('register_overflow', ()):
        if LOW <= record['exact'] <= HIGH:
            return False, checked
    return True, checked


# ---------------------------------------------------------------------------
# Certified runtime: same certificate binds program, domain, threshold
# ---------------------------------------------------------------------------
def run_certified(certificate, reading):
    domain = _normalized_domain(certificate['domain'])
    if set(reading) != {name for bounds, _ in domain for name in bounds}:
        return {'status': 'held_for_review', 'reason': 'reading_input_mismatch',
                'contract_id': certificate['contract_id'], 'reading': reading}
    if any(type(value) is not int or not LOW <= value <= HIGH for value in reading.values()):
        return {'status': 'held_for_review', 'reason': 'reading_outside_register',
                'contract_id': certificate['contract_id'], 'reading': reading}
    if not domain_contains(domain, reading):
        return {'status': 'held_for_review', 'reason': 'outside_signed_relation_domain',
                'contract_id': certificate['contract_id'], 'reading': reading}

    result = run({'program': certificate['program'], 'inputs': reading,
                  'limit': certificate['limit']})
    authorized = {clip['step'] for clip in certificate.get('named_clips', ())}
    illegal = [step for step, row in enumerate(result['trace'])
               if row['clipped'] and (certificate['kind'] == 'raw_exact' or step not in authorized)]
    if illegal:
        return {'status': 'held_for_review', 'reason': 'certificate_integrity_failure',
                'contract_id': certificate['contract_id'], 'reading': reading,
                'illegal_clipped_steps': illegal}

    response = {'status': 'certified', 'contract_id': certificate['contract_id'],
                'reading': reading, 'value': result['value'], 'decision': result['decision'],
                'trace': result['trace']}
    if certificate.get('named_clips'):
        response['named_clip_readings'] = [
            {'name': clip['name'], 'expression': clip['expression'], 'step': clip['step'],
             'stored': result['trace'][clip['step']]['stored'],
             'clipped': result['trace'][clip['step']]['clipped']}
            for clip in certificate['named_clips']]
    return response


def run(fixture):
    result = execute(fixture['program'], fixture['inputs'])
    return {**result, 'decision': 'open_review' if result['value'] >= fixture['limit'] else 'normal'}
