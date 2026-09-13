"""Factual accumulator checkpoints. Never turn arithmetic sums into a verdict."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
import struct


def yaw(v):
    return v[1] if isinstance(v, list) and len(v) == 3 else None


def angular_difference(after, before):
    if not isinstance(after, (int, float)) or not isinstance(before, (int, float)):
        return None
    return (after - before + 180) % 360 - 180


def consumer_sequences(rows):
    """Pair actual calls by identity and order; retain discrepancies as evidence."""
    groups, returns = {}, {}
    for row in rows:
        if row['event'] in ('consume', 'manager_before', 'manager_after', 'set_enter'):
            cid = row.get('consumer_id')
            if cid is not None:
                groups.setdefault(cid, []).append(row)
        elif row['event'] == 'set_return':
            returns.setdefault(row.get('set_id'), []).append(row)
    results, incomplete = [], []
    for cid, chain in groups.items():
        if [r['event'] for r in chain] != ['consume', 'manager_before', 'manager_after', 'set_enter']:
            incomplete.append(cid)
            continue
        consume, before, after, setter = chain
        paired = returns.get(setter['seq'], [])
        if len(paired) != 1:
            incomplete.append(cid)
            continue
        returned = paired[0]
        identity = (consume['thread'], consume['receiver'])
        sequence = chain + paired
        if (any((r['thread'], r['receiver']) != identity for r in sequence)
                or any(a['seq'] >= b['seq'] for a, b in zip(sequence, sequence[1:]))
                or any(r['rsp'] != consume['rsp'] for r in (before, after))
                or setter['rsp'] + 8 != consume['rsp']
                or returned['rsp'] + 0xB8 != setter['rsp']):
            incomplete.append(cid)
            continue
        checks = {
            'local_delta_equals_accumulator': before['local_delta'] == consume['accumulator'],
            'view_before_equals_control': before['view_rotation'] == consume['control_rotation'],
            'local_delta_zero_after_manager': after['local_delta'] == [0, 0, 0],
            'request_equals_manager_view': setter['requested_rotation'] == after['view_rotation'],
            'returned_rotation_equals_request': returned['control_rotation'] == setter['requested_rotation'],
        }
        delta, view = yaw(before['local_delta']), yaw(before['view_rotation'])
        expected = (view + delta) % 360 if isinstance(view, (float, int)) and isinstance(delta, (float, int)) else None
        checks['manager_yaw_equals_wrapped_add_exactly'] = expected is not None and yaw(after['view_rotation']) == expected
        results.append({'consumer_id': cid, 'sequences': [r['seq'] for r in sequence],
                        'checks': checks, 'accumulator_yaw': yaw(consume['accumulator']),
                        'view_before_yaw': view, 'view_after_yaw': yaw(after['view_rotation']),
                        'requested_yaw': yaw(setter['requested_rotation']),
                        'returned_yaw': yaw(returned['control_rotation'])})
    return {'complete': len(results), 'incomplete_or_mismatched_ids': incomplete,
            'check_counts': dict(Counter(k for r in results for k, v in r['checks'].items() if v)),
            'results': results}


def intervening_cycles(rows):
    """Count only contiguous, identity-matched add-through-clear sequences."""
    expected = ['add', 'write', 'history_copy', 'consume', 'manager_before',
                'manager_after', 'set_enter', 'set_return', 'write']
    complete = []
    for index, add in enumerate(rows):
        if add['event'] != 'add':
            continue
        chain = rows[index:index + len(expected)]
        if [r['event'] for r in chain] != expected:
            continue
        _, write, history, consume, before, after, setter, returned, clear = chain
        if (any((r['thread'], r['receiver']) != (add['thread'], add['receiver']) for r in chain)
                or write.get('writer') != 'native_add' or write.get('add_id') != add['seq']
                or write['rsp'] != add['rsp'] or write['caller'] != add['caller']
                or any(r.get('consumer_id') != consume['seq'] for r in (consume, before, after, setter))
                or returned.get('set_id') != setter['seq']
                or any(r['rsp'] != consume['rsp'] for r in (before, after))
                or setter['rsp'] + 8 != consume['rsp']
                or returned['rsp'] + 0xB8 != setter['rsp']
                or clear.get('writer') != 'tick_tail_clear' or clear['after'] != 0):
            continue
        complete.append({'add_seq': add['seq'], 'clear_seq': clear['seq'],
                         'caller_kind': add['caller_kind'],
                         'history_yaw_equals_written': history['copy_yaw'] == write['after'],
                         'consumed_yaw_equals_written': yaw(consume['accumulator']) == write['after'],
                         'cleared_yaw_equals_written': clear['before'] == write['after']})
    return {'exact_contiguous_cycles': len(complete), 'results': complete,
            'note': 'Nonmatching/partial intervals are excluded, not diagnosed as failures.'}


def analyze(rows):
    counts = Counter(r['event'] for r in rows)
    writers = Counter(r.get('writer', 'missing') for r in rows if r['event'] == 'write')
    native_callers = Counter(r.get('caller_kind', 'missing') for r in rows
                             if r['event'] == 'write' and r.get('writer') == 'native_add')
    setters, results = {}, []
    for row in rows:
        if row['event'] == 'set_enter':
            setters[row['seq']] = row
        elif row['event'] == 'set_return':
            start = setters.get(row.get('set_id'))
            if start and (start['thread'], start['receiver'], start['rsp']) == (
                    row['thread'], row['receiver'], row['rsp'] + 0xB8):
                before, requested, after = (yaw(start.get('control_rotation')),
                                           yaw(start.get('requested_rotation')),
                                           yaw(row.get('control_rotation')))
                results.append({'set_id': start['seq'], 'return_seq': row['seq'],
                                'caller': start['caller'], 'before_yaw': before,
                                'requested_yaw': requested, 'after_yaw': after,
                                'actual_yaw_change_wrapped': angular_difference(after, before),
                                'request_error_wrapped': angular_difference(after, requested)})
    return {'events': dict(counts), 'changed_writers': dict(writers),
            'native_add_callers': dict(native_callers),
            'capture_errors': [r for r in rows if r['event'] == 'capture_error'],
            'ended': bool(rows and rows[-1]['event'] == 'capture_end'),
            'end_reason': rows[-1].get('reason') if rows and rows[-1]['event'] == 'capture_end' else None,
            'setter_results': results,
            'consumer_sequences': consumer_sequences(rows),
            'intervening_cycles': intervening_cycles(rows),
            'limitations': ['Changed writes only; same-bit stores are omitted by GDB.',
                            'Initial/final intervals may be partial. No generation-local sums.',
                            'Control rotation is an intermediate state, not rendered camera pose.',
                            'Unknown writer PCs are after the write; inspect before choosing new sites.',
                            'Observer timing is perturbed; visible stall timing is supplied by the user.']}


def report(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result = analyze(rows)
    summary = path.with_suffix('.summary.json')
    summary.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    output = path.with_suffix('.events.csv')
    fields = ['seq', 'event', 'thread', 'receiver', 'pc', 'writer', 'caller', 'caller_kind',
              'add_id', 'consumer_id', 'set_id', 'sign_id', 'contribution', 'before', 'after',
              'accumulator_yaw', 'control_yaw', 'view_yaw', 'local_delta_yaw', 'requested_yaw',
              'computed_yaw_delta', 'comparison_zero', 'copy_yaw']
    with output.open('w', newline='') as file:
        writer = csv.DictWriter(file, fields)
        writer.writeheader()
        for row in rows:
            flat = {k: row.get(k) for k in fields}
            for target, source in [('accumulator_yaw', 'accumulator'), ('control_yaw', 'control_rotation'),
                                   ('view_yaw', 'view_rotation'), ('local_delta_yaw', 'local_delta'),
                                   ('requested_yaw', 'requested_rotation')]:
                flat[target] = yaw(row.get(source))
            writer.writerow(flat)
    return '\n'.join([str(summary), str(output),
                      'Events: ' + json.dumps(result['events']),
                      'Changed writes: ' + json.dumps(result['changed_writers']),
                      'Native-add callers: ' + json.dumps(result['native_add_callers']),
                      'Paired control-rotation calls: %d; errors: %d; end: %s' % (
                          len(result['setter_results']), len(result['capture_errors']), result['end_reason']),
                      'Raw checkpoints and user-visible reproduction are required; no automatic cause verdict.'])


def legacy_report(path, prefix):
    """Decode actual receiver snapshots; checkpoint equality is not a cause verdict."""
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    start = next(r for r in rows if r['event'] == 'capture_start')
    expected_target = start['game_base'] + 0x3564E20
    by_id = {r['seq']: r for r in rows}
    pairs = []
    for after in rows:
        if after['event'] not in ('x_mouse_after', 'x_gamepad_after'):
            continue
        before = by_id.get(after.get('output_id'))
        if not before or before['event'] != after['event'].replace('_after', '_output'):
            continue
        if before.get('output_target') != expected_target:
            raise ValueError('Legacy output target differs from the statically identified accumulator writer')
        identity = ('thread', 'rsp', 'receiver', 'camera_id')
        if any(before.get(k) != after.get(k) for k in identity) or before['seq'] >= after['seq']:
            raise ValueError('Mismatched legacy call boundary at seq %s' % after['seq'])
        def number(row, offset, fmt='d'):
            return struct.unpack_from('<'+fmt, bytes.fromhex(row['receiver_300_d6c']), offset-0x300)[0]
        pairs.append({'output_seq': before['seq'], 'after_seq': after['seq'],
                      'thread': before['thread'], 'receiver': before['receiver'],
                      'branch': before['branch'], 'target': before['output_target'],
                      'handler_output': before['output'], 'scale_540': number(before, 0x540, 'f'),
                      'accumulator_before': number(before, 0x530),
                      'accumulator_after': number(after, 0x530),
                      'control_yaw_before': number(before, 0x318),
                      'control_yaw_after': number(after, 0x318)})
    previous, checkpoints = {}, []
    for pair in pairs:
        key = (pair['thread'], pair['receiver'])
        if key in previous:
            last = previous[key]
            delta = angular_difference(pair['control_yaw_before'], last['control_yaw_after'])
            checkpoints.append({'from_output_seq': last['output_seq'], 'to_output_seq': pair['output_seq'],
                                'previous_accumulator': last['accumulator_after'],
                                'observed_control_yaw_change_wrapped': delta,
                                'exactly_matches_previous_accumulator': delta == last['accumulator_after']})
        previous[key] = pair
    result = {'source': str(path), 'paired_x_outputs': len(pairs),
              'accumulator_zero_before': sum(p['accumulator_before'] == 0 for p in pairs),
              'accumulator_changed': sum(p['accumulator_after'] != p['accumulator_before'] for p in pairs),
              'accumulator_nonzero_after': sum(p['accumulator_after'] != 0 for p in pairs),
              'successive_control_checkpoints': len(checkpoints),
              'exact_checkpoint_matches': sum(p['exactly_matches_previous_accumulator'] for p in checkpoints),
              'capture_errors': [r for r in rows if r['event'] == 'capture_error'],
              'pairs': pairs, 'checkpoints': checkpoints,
              'limitations': ['Offsets +530 and +318 use the matching shipping disassembly.',
                              'Controller checkpoints are not final rendered camera rotation.',
                              'Equality does not exclude intermediate writes or cancellations.',
                              'Perceived direction does not identify an Enhanced Input winner.']}
    output = prefix.with_suffix('.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    with prefix.with_suffix('.csv').open('w', newline='') as file:
        if pairs:
            writer = csv.DictWriter(file, list(pairs[0]))
            writer.writeheader()
            writer.writerows(pairs)
    return ('%s\nPaired X outputs: %d; changed accumulators: %d; nonzero after: %d\n'
            'Successive control checkpoints exactly matching preceding accumulator: %d/%d\n'
            'Controller state only; no rendered-pose or intermediate-write verdict.' % (
                output, len(pairs), result['accumulator_changed'], result['accumulator_nonzero_after'],
                result['exact_checkpoint_matches'], len(checkpoints)))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    parser.add_argument('--legacy-output', type=Path,
                        help='Decode prior broad-observer snapshots; write JSON/CSV at this prefix')
    args = parser.parse_args()
    print(legacy_report(args.trace, args.legacy_output) if args.legacy_output else report(args.trace))
