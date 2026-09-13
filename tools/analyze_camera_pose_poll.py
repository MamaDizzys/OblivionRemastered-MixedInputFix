"""Summarize asynchronous pose polls without treating stable reads as frames."""
import argparse
from collections import Counter
import csv
import json
from pathlib import Path
from analyze_camera_view import angular_difference


def analyze(rows):
    points, previous = [], None
    for row in rows:
        if row['event'] != 'pose_sample':
            continue
        pose = row['after']
        point = {k: row[k] for k in ('seq', 'host_time', 'read_span_ns', 'repeated_bytes_equal', 'skipped_deadlines')}
        point.update(control_yaw=pose['control_rotation'][1], cache_yaw=pose['cache_rotation'][1],
                     cache_stamp=pose['cache_stamp'])
        if row['repeated_bytes_equal'] and previous:
            point.update(previous_seq=previous['seq'], interval_seconds=point['host_time']-previous['host_time'],
                         control_yaw_change=angular_difference(point['control_yaw'], previous['control_yaw']),
                         cache_yaw_change=angular_difference(point['cache_yaw'], previous['cache_yaw']))
        previous = point if row['repeated_bytes_equal'] else None
        points.append(point)
    return {'events': dict(Counter(r['event'] for r in rows)),
            'repeated_reads_equal': sum(p['repeated_bytes_equal'] for p in points),
            'skipped_deadlines': sum(p['skipped_deadlines'] for p in points),
            'max_read_span_ns': max((p['read_span_ns'] for p in points), default=None),
            'capture_errors': [r for r in rows if r['event'] == 'capture_error'],
            'end_reason': rows[-1].get('reason') if rows and rows[-1]['event'] == 'capture_end' else None,
            'checkpoints': points,
            'limitations': ['Asynchronous reads may span updates even when repeated bytes match (including ABA).',
                            'Cache state does not establish that a view getter or renderer consumed it.',
                            'No automatic stall verdict; align with the user-visible symptom.',
                            'Sampling misses intervening writes and short events; host time is not game time.']}


def report(path):
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    result = analyze(rows)
    path.with_suffix('.summary.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    fields = ['seq', 'host_time', 'read_span_ns', 'repeated_bytes_equal', 'skipped_deadlines',
              'control_yaw', 'cache_yaw', 'cache_stamp', 'previous_seq', 'interval_seconds',
              'control_yaw_change', 'cache_yaw_change']
    with path.with_suffix('.poses.csv').open('w', newline='') as file:
        writer = csv.DictWriter(file, fields)
        writer.writeheader()
        writer.writerows(result['checkpoints'])
    return 'Samples: %d; repeated bytes equal: %d; errors: %d; end: %s\n%s\n%s' % (
        len(result['checkpoints']), result['repeated_reads_equal'], len(result['capture_errors']),
        result['end_reason'], path.with_suffix('.summary.json'), path.with_suffix('.poses.csv'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('trace', type=Path)
    print(report(parser.parse_args().trace))
