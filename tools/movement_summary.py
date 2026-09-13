"""Bounded movement trace summary. Raw JSONL remains the authoritative record."""
import json
from pathlib import Path


def token(row):
    return (row.get('thread'), row.get('observed_generation'), row.get('owner'), row.get('evaluation_frame'))


def number(v):
    return format(v, '.6g') if isinstance(v, (int, float)) else str(v)


def vector(v):
    return '(' + ','.join(number(n) for n in v.get('xyz', [])) + ')/t' + str(v.get('type'))


def report(path):
    rows = [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]
    ends = [r for r in rows if r['event'] == 'capture_end']
    errors = [r for r in rows if r['event'] == 'capture_error']
    dispatches = {r['dispatch_id']: r for r in rows if r['event'] == 'dispatch_begin'}
    directions = {}
    for r in rows:
        if r['event'].endswith('_entry') and 'direction' in r:
            d = dispatches.get(r.get('dispatch_id'))
            if d:
                directions.setdefault(d['action'], set()).add(r['direction'])
    names = {a: '/'.join(sorted(ds)) + '@' + hex(a) for a, ds in directions.items()}
    groups = {}
    for r in rows:
        if 'observed_generation' in r:
            groups.setdefault(token(r), []).append(r)
    meaningful = [rs for rs in groups.values() if any('direction' in r or r['event'] == 'consume_sum' for r in rs)]
    lines = ['MIF MOVE REPORT', 'file=' + str(path),
             'rows=%d end=%s errors=%d movement_windows=%d' %
             (len(rows), ends[-1]['reason'] if ends else 'OPEN/PARTIAL', len(errors), len(meaningful))]
    for e in errors:
        lines.append('ERROR ' + e.get('site', '?') + ': ' + e.get('error', '?'))
    if not directions:
        lines.append('NO movement action linked to dispatch; keep raw file for inspection.')
    for action, name in names.items():
        lines.append('ACTION ' + name)
    for rs in meaningful[:3]:
        first = rs[0]
        closed = any(r['event'] == 'window_end' and r.get('same_identity') for r in rs)
        lines.append('WINDOW gen=%s thread=%s owner=%s frame=%s complete=%s' %
                     (first['observed_generation'], first['thread'], hex(first.get('owner') or 0),
                      hex(first.get('evaluation_frame') or 0), closed))
        before = {}
        for r in rs:
            event = r['event']
            prefix = '#' + str(r['seq']) + ' '
            action = r.get('action')
            if event in ('mapping_input', 'merge_before', 'merge_after') and action in names:
                key = '%s/%s' % (r['key'], hex(r['key_identity']))
                tag = (r['mapping_frame'], r['instance'], r['key_identity'], r.get('component'))
                who = names[action]
                if event == 'mapping_input':
                    metadata = r.get('key_metadata', {})
                    lines.append(prefix + 'MAP ' + who + ' key=' + key + ' input=' + vector(r['mapping_input']) +
                                 ' caller=' + hex(r['caller']) + ' saved_frame=' + hex(r['saved_evaluation_frame']) +
                                 (' key_type=%s identity_match=%s' % (metadata.get('type'), metadata.get('identity_matches'))
                                  if metadata else ''))
                elif event == 'merge_before':
                    before[tag] = r
                else:
                    b = before.pop(tag, None)
                    lines.append(prefix + 'MERGE ' + who + ' key=' + key + ' policy=' + str(r['policy']) +
                                 ' c=' + str(r['component']) + ' candidate=' + number(r['candidate']) +
                                 ' acc=' + (number(b['accumulated']) if b else '?') + '->' + number(r['accumulated']))
            elif event in ('action_before', 'action_after', 'dispatch_begin') and action in names:
                text = prefix + event.upper() + ' ' + names[action] + ' I=' + hex(r['instance']) + ' value=' + vector(r['value'])
                if event == 'dispatch_begin':
                    text += ' B=' + hex(r['binding']) + ' id=' + str(r['dispatch_id'])
                lines.append(text)
            elif 'direction' in r:
                text = prefix + event + ' object=' + hex(r['object']) + ' dispatch=' + str(r.get('dispatch_id'))
                if 'input' in r:
                    text += ' input=' + vector(r['input'])
                if 'raw_float' in r:
                    text += ' raw=' + number(r['raw_float']) + ' getter=' + str(r['getter_result']) + ' global=' + str(r['global_input_type'])
                text += ' caches[F,B,L,R]=' + ','.join(number(r['caches'][d]) for d in ('forward', 'backward', 'left', 'right'))
                lines.append(text)
            elif event == 'consume_sum':
                lines.append(prefix + 'SUM object=' + hex(r['object']) + ' forward=' + number(r['forward_sum']) + ' right=' + number(r['right_sum']))
        if before:
            lines.append('PARTIAL: unmatched merge-before events; inspect raw trace.')
    if len(meaningful) > 3:
        lines.append('Additional windows retained in raw trace.')
    if len(lines) > 149:
        lines = lines[:148] + ['REPORT TRUNCATED at 150 lines; raw file retains omitted events.']
    lines.append('END MIF MOVE REPORT')
    return '\n'.join(lines)


if __name__ == '__main__':
    import sys
    print(report(Path(sys.argv[1])))
