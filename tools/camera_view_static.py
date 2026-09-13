"""Validate the returned-view checkpoint against the exact shipping PE."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
from camera_accumulator_static import Image, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    parser.add_argument('--output', type=Path, default=Path('build/camera/pose/static'))
    parser.add_argument('--downstream', action='store_true', help='Validate post-getter callbacks and scene-view construction')
    args = parser.parse_args()
    sites = json.loads(Path(__file__).with_name(
        'camera_view_downstream.json' if args.downstream else 'camera_view_sites.json').read_text())
    if args.downstream:
        args.output = args.output / 'downstream'
    image = Image(args.exe)
    digest = validate(image, sites)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, (start, end) in sites['static_ranges'].items():
        with (args.output / (name + '.asm')).open('w') as file:
            subprocess.run(['objdump', '-d', '--insn-width=16',
                            '--start-address=%#x' % (image.base + start),
                            '--stop-address=%#x' % (image.base + end), str(args.exe)],
                           stdout=file, check=True)
    links = []
    tables = [('localplayer', 0x7702178)] if args.downstream else [
        ('controller', 0x7BDE600), ('controller', 0x7C35C30), ('manager', 0x7BD8D90)]
    for kind, vt in tables:
        observed = {slot: struct.unpack('<Q', image.read(vt + int(slot, 16), 8))[0] - image.base
                    for slot in sites[kind + '_slots']}
        if observed != sites[kind + '_slots']:
            raise ValueError('Static vtable link differs: %#x' % vt)
        links.append({'kind': kind, 'vtable_rva': hex(vt),
                      'targets_rva': {s: hex(v) for s, v in observed.items()}})
    (args.output / 'validation.json').write_text(json.dumps({
        'game_sha256': digest, 'probes': len(sites['sites']), 'guards': len(sites['guards']),
        'links': links, 'note': 'Static linkage only; not proof of a live scene-view path or a stall.'
    }, indent=2) + '\n')
    print('Validated shipping hash, view bytes and vtable links; ' + str(args.output))


if __name__ == '__main__':
    main()
