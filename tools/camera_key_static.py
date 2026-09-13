"""Reconstruct the early EKeys name layout against known live journal anchors.

This is a checked static inference, not a general numeric-FName lookup table.
Use camera_key_probe.py to confirm names directly from the current live pool.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from analyze_camera_prototype import analyze
from camera_accumulator_static import Image
from camera_key_probe import GAME_HASH, GUARDS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    parser.add_argument('journal', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    image = Image(args.exe)
    if hashlib.sha256(image.data).hexdigest() != GAME_HASH:
        raise ValueError('Unexpected executable hash')
    for rva, value in GUARDS.items():
        assert image.read(rva, len(bytes.fromhex(value))) == bytes.fromhex(value)
    args.output.mkdir(parents=True, exist_ok=True)
    asm = subprocess.check_output(['objdump', '-d', '-Mintel',
        f'--start-address={image.base + 0x8FF000:#x}',
        f'--stop-address={image.base + 0x906000:#x}', str(args.exe)], text=True)
    (args.output / 'key-initializers.asm').write_text(asm)
    rows = []
    lines = asm.splitlines()
    for i, line in enumerate(lines):
        if 'call   0x140f3b740' not in line:
            continue
        block = '\n'.join(lines[max(0, i - 6):i])
        names = re.findall(r'lea    rdx,.*# (0x[0-9a-f]+)', block)
        globals_ = re.findall(r'lea    rcx,.*# (0x[0-9a-f]+)', block)
        if not names or not globals_:
            continue
        name = image.read(int(names[-1], 16) - image.base, 100).split(b'\0')[0].decode('ascii')
        rows.append({'name': name, 'global': globals_[-1], 'constructor_call': line.strip().split(':')[0]})
    ordered = sorted((r for r in rows if 0x1491132C0 <= int(r['global'], 16) <= 0x149113F38),
                     key=lambda r: int(r['global'], 16))
    # This slot copies Delete's existing FKey; it does not intern another name.
    assert image.read(0x902990, 14) == bytes.fromhex('48 8B 05 B1 0B 81 08 48 89 05 0A 15 81 08')
    assert [int(r['global'], 16) for r in ordered] == [
        g for g in range(0x1491132C0, 0x149113F38 + 1, 0x18) if g != 0x149113EA8]
    summary = analyze(args.journal.read_bytes())
    evidence = [r['inventory'] for r in summary['first_rejections'] if r.get('inventory')]
    if not evidence:
        raise ValueError('Expected a granular live inventory journal')
    anchor = evidence[0]
    index = int(anchor['mouse_x'], 16)
    inferred = {}
    for row in ordered:
        row['inferred_live_identity'] = hex(index)
        inferred[row['name']] = index
        index += (len(row['name']) + 3) // 2  # 2-byte header, ANSI bytes, align 2.
    anchors = {'mouse_x': 'MouseX', 'mouse_y': 'MouseY',
               'gamepad_x': 'Gamepad_RightX', 'gamepad_y': 'Gamepad_RightY'}
    for item in evidence:
        if any(inferred[name] != int(item[field], 16) for field, name in anchors.items()):
            raise ValueError('Runtime anchors do not support sequential-name reconstruction')
    by_id = {r['inferred_live_identity']: r for r in ordered}
    result = {'game_sha256': GAME_HASH,
        'qualification': 'Static sequential-name reconstruction agrees with all supplied runtime anchors; '
                         'direct live pool confirmation is pending. Never hardcode these FName indices.',
        'anchors': {name: hex(inferred[name]) for name in anchors.values()},
        'rejected_keys': [by_id.get(e['key'], {'unresolved': e['key']}) for e in evidence],
        'key_name_layout': ordered}
    (args.output / 'static-key-identities.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'key_name_layout'}, indent=2))


if __name__ == '__main__':
    main()
