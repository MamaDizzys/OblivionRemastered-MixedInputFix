"""Validate accumulator sites and preserve static evidence from the exact PE.

Uses local objdump and Python's standard library. Optional --scan streams .text
and keeps direct field/nearby/vector/alias candidates, not a type-aware proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess


class Image:
    def __init__(self, path):
        self.path, self.data = path, path.read_bytes()
        pe = struct.unpack_from('<I', self.data, 0x3C)[0]
        if self.data[:2] != b'MZ' or self.data[pe:pe+4] != b'PE\0\0':
            raise ValueError('Expected PE image')
        opt = pe + 24
        self.base = struct.unpack_from('<Q', self.data, opt + 24)[0]
        self.sections = []
        for i in range(struct.unpack_from('<H', self.data, pe + 6)[0]):
            h = opt + struct.unpack_from('<H', self.data, pe + 20)[0] + 40*i
            _, rva, size, offset = struct.unpack_from('<4I', self.data, h + 8)
            self.sections.append((rva, size, offset))

    def read(self, rva, size):
        for start, length, offset in self.sections:
            if start <= rva and rva + size <= start + length:
                return self.data[offset+rva-start:offset+rva-start+size]
        raise ValueError('RVA outside file sections: 0x%x' % rva)


def validate(image, sites):
    digest = hashlib.sha256(image.data).hexdigest()
    if digest != sites['game_sha256'] or image.base != sites['image_base']:
        raise ValueError('Shipping image hash/base differs from the investigated build')
    for name, site in sites['sites'].items():
        expected = bytes.fromhex(site['bytes'])
        if image.read(site['rva'], len(expected)) != expected:
            raise ValueError('Probe mismatch: ' + name)
    for rva, signature in sites['guards'].items():
        expected = bytes.fromhex(signature)
        if image.read(int(rva, 16), len(expected)) != expected:
            raise ValueError('Guard mismatch: ' + rva)
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exe', type=Path)
    parser.add_argument('--output', type=Path, default=Path('build/camera/accumulator/static'))
    parser.add_argument('--scan', action='store_true')
    args = parser.parse_args()
    sites = json.loads(Path(__file__).with_name('camera_accumulator_sites.json').read_text())
    image = Image(args.exe)
    digest = validate(image, sites)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, (start, end) in sites['static_ranges'].items():
        with (args.output / (name + '.asm')).open('w') as file:
            subprocess.run(['objdump', '-d', '--insn-width=16',
                            '--start-address=%#x' % (image.base + start),
                            '--stop-address=%#x' % (image.base + end), str(args.exe)],
                           stdout=file, check=True)
    # Every on-disk occurrence of the observed function pointer, with the
    # hypothesized vtable start inferred from its known output slot.
    links = []
    needle = struct.pack('<Q', image.base + 0x3564E20)
    for start, size, offset in image.sections:
        position = image.data.find(needle, offset, offset+size)
        while position != -1:
            slot = start + position - offset
            vt = slot - 0xD18
            links.append({'output_slot_va': hex(image.base+slot), 'inferred_vtable_va': hex(image.base+vt),
                          'targets': {hex(k): hex(struct.unpack('<Q', image.read(vt+k, 8))[0])
                                      for k in (0x760, 0x768, 0xBE0, 0xC00, 0xD18)}})
            position = image.data.find(needle, position+1, offset+size)
    (args.output/'vtable-links.json').write_text(json.dumps(links, indent=2)+'\n')
    if args.scan:
        # Includes eight-byte yaw, overlapping vectors, and LEA aliases. Many
        # matches refer to unrelated objects/stack frames. Do not instrument all.
        pattern = re.compile(r'0x(?:51[89a-f]|52[0-9a-f]|53[0-7])\(')
        with (args.output / 'field-candidates.asm').open('w') as file:
            process = subprocess.Popen(['objdump', '-d', '--insn-width=16', '-j', '.text', str(args.exe)],
                                       stdout=subprocess.PIPE, text=True)
            for line in process.stdout:
                if pattern.search(line):
                    file.write(line)
            if process.wait():
                raise RuntimeError('objdump scan failed')
    (args.output / 'validation.json').write_text(json.dumps({
        'game_sha256': digest, 'probes': len(sites['sites']), 'guards': len(sites['guards']),
        'scan': args.scan, 'note': 'Direct-displacement candidates are not exhaustive alias/type analysis.'}, indent=2)+'\n')
    print('Validated %d probes and %d guards; %s\n%s' % (
        len(sites['sites']), len(sites['guards']), digest, args.output))


if __name__ == '__main__':
    main()
