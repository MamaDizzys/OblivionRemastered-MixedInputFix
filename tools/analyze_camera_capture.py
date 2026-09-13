#!/usr/bin/env python3
"""Summarize GDB camera observations without treating cancellation as a stall."""
import argparse
from collections import defaultdict
import csv
import json
import math
from pathlib import Path


def numeric(value):
    return isinstance(value, (int, float)) and math.isfinite(value)


def token(row):
    p = row.get('provenance', {})
    return (row.get('thread'), p.get('generation'), row.get('owner', p.get('owner')),
            row.get('frame', row.get('evaluation_frame', p.get('frame'))))


def analyze(rows):
    dispatches, cameras = {}, {}
    windows = {}
    modifiers = {}
    changes = []
    errors = []
    ended_threads = defaultdict(set)
    last_reset = {}
    outputs = []
    output_rows = {}
    receiver_changes = []
    started = set()
    for row in rows:
        event = row['event']
        if event == 'capture_error':
            errors.append(row)
        if event == 'reset':
            if token(row)[1] and row.get('provenance', {}).get('valid'):
                started.add(token(row))
            thread = row['thread']
            if thread in last_reset:
                ended_threads[thread].add(last_reset[thread])
            last_reset[thread] = token(row)
        if event == 'dispatch_begin':
            dispatches[row['dispatch_id']] = dict(row, camera_calls=[], cleared_axes=[])
        elif event == 'dispatch_end' and row.get('dispatch_id') in dispatches:
            dispatches[row['dispatch_id']]['returned'] = True
        elif event in ('x_clear', 'y_clear') and row.get('dispatch_id') in dispatches:
            dispatches[row['dispatch_id']]['cleared_axes'].append(row['axis'])
        elif event in ('x_entry', 'y_entry'):
            cameras[row['seq']] = dict(row, output_ids=[])
            if row.get('dispatch_id') in dispatches:
                dispatches[row['dispatch_id']]['camera_calls'].append(row['seq'])
        elif event in ('x_branch', 'y_branch') and row.get('camera_id') in cameras:
            cameras[row['camera_id']]['getter_result'] = row['getter_result']
            cameras[row['camera_id']]['branch_provenance'] = row.get('provenance', {})
            cameras[row['camera_id']]['common_type'] = row.get('common_type')
        elif event in ('x_return', 'y_return') and row.get('camera_id') in cameras:
            cameras[row['camera_id']].update(returned=True, return_state=row.get('state'))
        elif event.endswith('_output'):
            output_rows[row['seq']] = row
            camera = cameras.get(row.get('camera_id'), {})
            if camera:
                camera['output_ids'].append(row['seq'])
            dispatch = dispatches.get(row.get('dispatch_id'), {})
            scope = row.get('provenance', {}).get('scope', {})
            outputs.append({'seq': row['seq'], 'thread': row.get('thread'), 'generation': token(row)[1],
                            'owner': token(row)[2], 'frame': token(row)[3],
                            'label': row.get('label'), 'axis': row['axis'], 'camera': row['camera'],
                            'dispatch_id': row.get('dispatch_id'), 'camera_id': row.get('camera_id'),
                            'action': dispatch.get('action'), 'instance': dispatch.get('instance'),
                            'binding': dispatch.get('binding'), 'branch': row.get('branch'),
                            'getter_result': camera.get('getter_result'),
                            'common_type': camera.get('common_type'),
                            'snapshot_source': scope.get('source'), 'snapshot_axis': scope.get('axis'),
                            'snapshot_generation': scope.get('generation'), 'snapshot_frame': scope.get('frame'),
                            'generation_matches': scope.get('generation_matches'),
                            'dispatch_value': dispatch.get('value', {}).get('xyz', [None])[0],
                            'handler_input': camera.get('input', {}).get('xyz', [None])[0],
                            'output': row['output'], 'state': row.get('state'),
                            'output_target': row.get('output_target')})
        elif event in ('x_gamepad_after', 'x_mouse_after', 'y_gamepad_after', 'y_mouse_after'):
            before = output_rows.get(row.get('output_id'))
            if before and before.get('receiver') == row.get('receiver'):
                a, b = (bytes.fromhex(r.get('receiver_300_d6c', '')) for r in (before, row))
                if len(a) == len(b) == 0xA6C:
                    receiver_changes.append({'output_id': before['seq'], 'after_seq': row['seq'],
                        'receiver': row['receiver'], 'axis': row['axis'],
                        'changed_words': [{'offset': hex(0x300+i), 'before': a[i:i+4].hex(),
                                           'after': b[i:i+4].hex()}
                                          for i in range(0, len(a), 4) if a[i:i+4] != b[i:i+4]]})
        elif event == 'action_before':
            modifiers[(token(row), row['instance'])] = row
        elif event == 'action_after':
            before = modifiers.pop((token(row), row['instance']), None)
            if before:
                changes.append({'thread': row.get('thread'), 'generation': token(row)[1],
                                'action': row['action'], 'instance': row['instance'],
                                'before': before['value'], 'after': row['value'],
                                'changed': before['value'] != row['value']})
        if event in ('mapping_input', 'merge_before', 'merge_after'):
            key = token(row)
            win = windows.setdefault(key, {'mappings': [], 'dispatches': []})
            win['mappings'].append({k: v for k, v in row.items() if k not in ('host_time', 'rsp')})
    for dispatch in dispatches.values():
        if dispatch['camera_calls'] or dispatch['cleared_axes']:
            windows.setdefault(token(dispatch), {'mappings': [], 'dispatches': []})['dispatches'].append(dispatch)
    counts = []
    for key, win in windows.items():
        groups = defaultdict(list)
        for dispatch in win['dispatches']:
            axes = {cameras[c]['axis'] for c in dispatch['camera_calls']} | set(dispatch['cleared_axes'])
            for axis in axes:
                groups[(dispatch['action'], axis)].append(dispatch)
        for (action, axis), group in groups.items():
            counts.append({'thread': key[0], 'generation': key[1], 'owner': key[2], 'frame': key[3],
                           'action': action, 'axis': axis, 'dispatch_count': len(group),
                           'camera_handler_calls': sum(sum(cameras[c]['axis'] == axis for c in d['camera_calls']) for d in group),
                           'bindings': sorted({d['binding'] for d in group}),
                           'instances': sorted({d['instance'] for d in group}),
                           'dispatch_ids': [d['dispatch_id'] for d in group],
                           'closed_by_next_reset': key in ended_threads[key[0]],
                           'complete_window': key in started and key in ended_threads[key[0]],
                           'note': 'Counts cover captured generation window; nested reset invalidates older windows.'})
    sums = defaultdict(list)
    for row in outputs:
        sums[(row['thread'], row['generation'], row['owner'], row['frame'], row['camera'], row['axis'])].append(row)
    aggregate = []
    for key, group in sums.items():
        values = [r['output'] for r in group if numeric(r['output'])]
        aggregate.append({'thread': key[0], 'generation': key[1], 'owner': key[2], 'frame': key[3],
                          'camera': key[4], 'axis': key[5], 'output_calls': len(group),
                          'branches': [r['branch'] for r in group],
                          'actions': sorted({r['action'] for r in group if r['action'] is not None}),
                          'has_opposing_outputs': any(v > 0 for v in values) and any(v < 0 for v in values),
                          'arithmetic_sum': sum(values) if len(values) == len(group) else None,
                          'complete_window': key[:4] in started and key[:4] in ended_threads[key[0]],
                          'note': 'Sum is diagnostic only; downstream accumulation semantics require target inspection.'})
    return {'capture_errors': errors, 'capture_ended': any(r['event'] == 'capture_end' for r in rows),
            'end_reason': next((r.get('reason') for r in reversed(rows) if r['event'] == 'capture_end'), None),
            'complete_windows': len(started & set().union(*ended_threads.values())),
            'handler_calls': list(cameras.values()), 'receiver_changes': receiver_changes,
            'dispatch_counts': counts,
            'relevant_dispatches': [d for d in dispatches.values() if d['camera_calls'] or d['cleared_axes']],
            'camera_outputs': outputs, 'output_groups': aggregate,
            'action_modifier_changes': changes,
            'mapping_windows': [dict(thread=k[0], generation=k[1], owner=k[2], frame=k[3], mappings=v['mappings']) for k, v in windows.items()],
            'interpretation': 'No automatic stall/cause verdict. Compare mappings, modifiers, callbacks, branch history and actual target state; X/Y stay separate.'}


def summarize(capture, output=None):
    with capture.open() as stream:
        rows = [json.loads(line) for line in stream if line.strip()]
    result = analyze(rows)
    output = output or capture.with_suffix('.summary.json')
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    csv_path = output.with_suffix('.outputs.csv')
    with csv_path.open('w', newline='') as stream:
        fields = ['thread', 'generation', 'label', 'axis', 'camera', 'dispatch_id', 'action', 'instance', 'binding',
                  'branch', 'getter_result', 'common_type', 'snapshot_source', 'snapshot_axis', 'snapshot_generation', 'snapshot_frame', 'generation_matches',
                  'dispatch_value', 'handler_input', 'output', 'output_target']
        writer = csv.DictWriter(stream, fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(result['camera_outputs'])
    return result, output, csv_path


def report(capture, output=None):
    result, output, csv_path = summarize(capture, output)
    lines = [str(capture), 'end=%s complete_windows=%d errors=%d' %
             (result['end_reason'], result['complete_windows'], len(result['capture_errors'])),
             'Full summary: ' + str(output), 'Outputs CSV: ' + str(csv_path),
             'Host timing is debugger-perturbed. Arithmetic sums do not establish downstream cancellation.']
    lines.extend('ERROR ' + str(e) for e in result['capture_errors'])
    for d in result['dispatch_counts']:
        lines.append('COUNT gen=%s %s action=%s dispatches=%d handlers=%d complete=%s' %
                     (d['generation'], d['axis'], d['action'], d['dispatch_count'],
                      d['camera_handler_calls'], d['complete_window']))
    relevant = {c.get('action') for c in result['relevant_dispatches']}
    for change in result['action_modifier_changes']:
        if change['changed'] and change['action'] in relevant:
            lines.append('MOD gen=%s action=%s %s -> %s' % (change['generation'], change['action'],
                         change['before']['xyz'], change['after']['xyz']))
    for c in result['handler_calls']:
        if not c['output_ids']:
            lines.append('NO_OUTPUT seq=%s %s input=%s returned=%s getter=%s' %
                         (c['seq'], c['axis'], c['input']['xyz'], c.get('returned', False), c.get('getter_result')))
    for o in result['camera_outputs']:
        lines.append('OUT seq=%s gen=%s %s action=%s binding=%s source=%s/%s valid=%s getter=%s global=%s input=%s out=%s state=%s' %
                     (o['seq'], o['generation'], o['axis'], o['action'], o['binding'],
                      o['snapshot_source'], o['snapshot_axis'], o['generation_matches'], o['getter_result'],
                      o['common_type'], o['handler_input'], o['output'], o['state']))
    if len(lines) > 150:
        lines = lines[:149] + ['TRUNCATED; preserve raw JSONL and full summary/CSV listed above.']
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path, help='Summary JSON (default: capture.summary.json)')
    args = parser.parse_args()
    print(report(args.capture, args.output))


if __name__ == '__main__':
    main()
