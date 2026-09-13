"""Read committed prototype records; prove native output pairs, not just candidates."""
import argparse
import collections
import json
from pathlib import Path
import struct

RECORD = struct.Struct('<9Q6d6I')
INVENTORY = struct.Struct('<13Q2I5i7I')
INVENTORY_FIELDS = ('maps mapping mapping_action key modifiers layout candidate_mapping candidate_action '
                    'candidate_instance mouse_x mouse_y gamepad_x gamepad_y subreason read_mask count '
                    'mapping_index trigger_count modifier_count candidate_index candidate_count source source_axis '
                    'candidate_valid candidate_source candidate_axis flags').split()
INVENTORY_REASONS = ('none maps_read maps_null count_read count_negative count_limit action_read source_axis '
                     'source_unknown triggers_read triggers_nonempty key_read modifiers_read modifier_count_read '
                     'modifier_count_negative modifier_count_limit flags_read candidate_invalid candidate_instance '
                     'candidate_axis candidate_source orphan_invalid orphan_before orphan_after orphan_alignment '
                     'action_missing digital_candidate').split()
READ_FIELDS = ('maps count mapping_action trigger_count key modifiers modifier_count flags '
               'mouse_x mouse_y gamepad_x gamepad_y').split()
AXES = {0: 'Unknown', 1: 'X', 2: 'Y'}
SOURCES = {0: 'Unknown', 1: 'Mouse', 2: 'Gamepad', 3: 'Digital', 4: 'LeftStick'}
FIELDS = ('sequence generation frame owner action instance receiver call target '
          'mouse stick input angular before after event axis source reason thread flags').split()
REASONS = ('ok no_dispatch stale unsupported mappings unobserved inactive mode identity cold '
           'duplicate nested changed overflow output_mismatch').split()


def inventory_detail(r):
    e = r['inventory'].copy()
    subreason = e.pop('subreason')
    e['subreason'] = INVENTORY_REASONS[subreason] if subreason < len(INVENTORY_REASONS) else subreason
    e['readable_fields'] = [name for bit, name in enumerate(READ_FIELDS) if e['read_mask'] & (1 << bit)]
    for name in READ_FIELDS:
        if name not in e['readable_fields']:
            e[name] = None
    for name in INVENTORY_FIELDS[:13]:
        if e[name] is not None:
            e[name] = hex(e[name])
    e['layout_hash_at_rejection'] = e.pop('layout')
    e['source_name'] = SOURCES.get(e['source'], e['source'])
    e['source_axis_name'] = AXES.get(e['source_axis'], e['source_axis'])
    if e['candidate_index'] < 0:
        for name in ('candidate_mapping', 'candidate_action', 'candidate_instance', 'candidate_valid',
                     'candidate_source', 'candidate_axis'):
            e[name] = None
    e['assumed_layout'] = {'owner_maps_offset': '0x548', 'owner_count_offset': '0x550',
                           'mapping_stride': '0x50', 'action_offset': '0x20', 'key_offset': '0x28',
                           'trigger_count_offset': '0x8', 'modifiers_offset': '0x10',
                           'modifier_count_offset': '0x18', 'flags_offset': '0x40'}
    e['dispatch'] = {k: hex(r[k]) for k in ('frame', 'owner', 'action', 'instance', 'receiver')}
    e['thread'] = r['thread']
    return e


def analyze(data):
    if len(data) < 64 or data[:8] != b'MIFCAM01':
        raise ValueError('Not a camera prototype journal')
    version, stride, capacity, pid, claimed, game = struct.unpack_from('<4I2Q', data, 8)
    expected_stride = {1: RECORD.size, 2: RECORD.size + INVENTORY.size}.get(version)
    if stride != expected_stride or capacity != 4096 or len(data) != 64 + stride * capacity:
        raise ValueError('Unexpected journal layout or incomplete file')
    records = []
    for i in range(min(claimed, capacity)):
        r = dict(zip(FIELDS, RECORD.unpack_from(data, 64+i*stride)))
        if version == 2:
            r['inventory'] = dict(zip(INVENTORY_FIELDS, INVENTORY.unpack_from(data, 64+i*stride+RECORD.size)))
        if r['sequence'] == i+1:
            records.append(r)
    groups = collections.defaultdict(list)
    rejections = []
    for r in records:
        if r['event'] == 1:
            rejection = {'reason': REASONS[r['reason']] if r['reason'] < len(REASONS) else r['reason'],
                         'generation': r['generation'], 'axis': r['axis'], 'axis_name': AXES.get(r['axis'], r['axis'])}
            if r['reason'] == 4 and version == 2:
                rejection['inventory'] = inventory_detail(r)
            rejections.append(rejection)
        elif r['call']:
            groups[r['call']].append(r)
    pairs = []
    for call, rows in groups.items():
        begin = [r for r in rows if r['event'] == 2]
        outputs = [r for r in rows if r['event'] == 3]
        end = [r for r in rows if r['event'] == 4]
        if len(begin) != 1 or len(end) != 1 or len(outputs) != 2:
            continue
        if end[0]['reason'] or end[0]['flags'] != 0x101 or {r['source'] for r in outputs} != {1, 2}:
            continue
        key = ('generation', 'owner', 'frame', 'action', 'instance', 'receiver', 'axis', 'thread')
        if any(any(r[k] != begin[0][k] for k in key) for r in outputs + end):
            continue
        if any(r['reason'] or not r['flags'] or not r['angular'] or r['after'] == r['before'] for r in outputs):
            continue
        # Same native target, no accumulator clear between observed source calls.
        if outputs[0]['target'] != outputs[1]['target'] or outputs[0]['after'] != outputs[1]['before']:
            continue
        pairs.append({'call': call, **{k: begin[0][k] for k in key},
                      'mouse_candidate': begin[0]['mouse'], 'stick_candidate': begin[0]['stick'],
                      'outputs': [{k: r[k] for k in ('source', 'target', 'input', 'angular', 'before', 'after')}
                                  for r in outputs]})
    return {'pid': pid, 'game': hex(game), 'version': version, 'records': len(records), 'claimed': claimed,
            'saturated': claimed > capacity, 'verified_pairs': pairs, 'first_rejections': rejections,
            'note': 'A pair requires two nonzero native outputs and consecutive accumulator changes in one evaluation/receiver/axis. '
                    'Synthetic fixture journals are standalone evidence, not live-game validation.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('journal', type=Path)
    p.add_argument('--output', type=Path)
    args = p.parse_args()
    result = analyze(args.journal.read_bytes())
    output = args.output or args.journal.with_suffix('.summary.json')
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(f"{result['records']} committed records; {len(result['verified_pairs'])} verified native output pairs; "
          f"saturated={result['saturated']}")
    if result['verified_pairs']:
        pair = result['verified_pairs'][0]
        print(f"First pair: generation {pair['generation']}, axis {pair['axis']}, call {pair['call']}")
        for r in pair['outputs']:
            print(f"  source={r['source']} input={r['input']:.9g} angular={r['angular']:.9g} "
                  f"accumulator={r['before']:.9g} -> {r['after']:.9g}")
    print(output)


if __name__ == '__main__':
    main()
