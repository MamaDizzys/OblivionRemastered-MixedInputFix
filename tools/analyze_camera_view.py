"""Compare co-observed controller and returned camera-view checkpoints."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path


def yaw(rotation):
    return rotation[1] if isinstance(rotation, list) and len(rotation) == 3 else None


def angular_difference(after, before):
    if not isinstance(after, (int, float)) or not isinstance(before, (int, float)):
        return None
    return (after - before + 180) % 360 - 180


def analyze(rows):
    previous, points, groups = {}, [], {}
    for row in rows:
        if row['event'] != 'view_return':
            continue
        key = (row['thread'], row['controller'], row['manager'], row['caller'])
        last = previous.get(key)
        point = {k: row[k] for k in ('seq', 'host_time', 'thread', 'controller', 'manager', 'caller', 'cache_stamp')}
        point.update(control_yaw=yaw(row['control_rotation']), view_yaw=yaw(row['returned_rotation']),
                     cache_yaw=yaw(row['cache_rotation']),
                     returned_rotation_equals_cache=row['returned_rotation'] == row['cache_rotation'])
        if last:
            point.update(previous_seq=last['seq'], host_interval_seconds=row['host_time'] - last['host_time'],
                         control_yaw_change=angular_difference(point['control_yaw'], yaw(last['control_rotation'])),
                         view_yaw_change=angular_difference(point['view_yaw'], yaw(last['returned_rotation'])),
                         cache_stamp_changed=row['cache_stamp'] != last['cache_stamp'])
        previous[key] = row
        points.append(point)
        group = groups.setdefault(key, {'thread': row['thread'], 'controller': row['controller'],
                                       'manager': row['manager'], 'caller': row['caller'],
                                       'calls': 0, 'transitions': 0, 'control_yaw_changes': 0,
                                       'view_yaw_changes': 0, 'equal_yaw_changes': 0})
        group['calls'] += 1
        if last:
            group['transitions'] += 1
            group['control_yaw_changes'] += point['control_yaw_change'] not in (None, 0)
            group['view_yaw_changes'] += point['view_yaw_change'] not in (None, 0)
            group['equal_yaw_changes'] += (point['control_yaw_change'] is not None
                                           and point['control_yaw_change'] == point['view_yaw_change'])
    return {'events': dict(Counter(r['event'] for r in rows)),
            'callers': dict(Counter(hex(p['caller']) for p in points)),
            'caller_checkpoints': list(groups.values()),
            'observed_host_span_seconds': points[-1]['host_time'] - points[0]['host_time'] if points else None,
            'distinct_cache_stamp_values': len(set(p['cache_stamp'] for p in points)),
            'returned_rotation_equals_cache': sum(p['returned_rotation_equals_cache'] for p in points),
            'capture_errors': [r for r in rows if r['event'] == 'capture_error'],
            'end_reason': rows[-1].get('reason') if rows and rows[-1]['event'] == 'capture_end' else None,
            'checkpoints': points,
            'limitations': ['Returned manager view is downstream of control rotation, not proof of a rendered frame.',
                            'One getter may be called several times per frame; callers are kept separate.',
                            'Controller and view need not match exactly: camera offsets, lag and mode can be legitimate.',
                            'Bypass paths and later view modifications are outside this checkpoint.',
                            'GDB host intervals are not game-frame durations. User supplies visible symptom timing.']}


def report(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result = analyze(rows)
    summary, output = path.with_suffix('.summary.json'), path.with_suffix('.views.csv')
    summary.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    fields = ['seq', 'host_time', 'thread', 'controller', 'manager', 'caller', 'cache_stamp',
              'control_yaw', 'view_yaw', 'cache_yaw', 'returned_rotation_equals_cache', 'previous_seq',
              'host_interval_seconds', 'control_yaw_change', 'view_yaw_change', 'cache_stamp_changed']
    with output.open('w', newline='') as file:
        writer = csv.DictWriter(file, fields)
        writer.writeheader()
        writer.writerows(result['checkpoints'])
    return '\n'.join([str(summary), str(output), 'Events: ' + json.dumps(result['events']),
                      'Returned rotation equals cache: %d/%d; errors: %d; end: %s' % (
                          result['returned_rotation_equals_cache'], len(result['checkpoints']),
                          len(result['capture_errors']), result['end_reason']),
                      'Compare motion over successive same-caller checkpoints with the user-visible symptom.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    print(report(parser.parse_args().trace))
