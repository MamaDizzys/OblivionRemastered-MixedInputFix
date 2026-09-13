"""Validate prototype signatures and extract shipping code for the standalone fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
from camera_accumulator_static import Image

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('exe', type=Path)
p.add_argument('--output', type=Path, default=Path('build/camera-prototype'))
args = p.parse_args()
im = Image(args.exe)
digest = hashlib.sha256(im.data).hexdigest()
assert digest == 'b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457'
source = Path('src/CameraSites.hpp').read_text()
signatures = re.findall(r'\{(0x[0-9A-F]+), "([0-9A-F ]+)", "([^"]+)"\}', source)
for rva, hexbytes, label in signatures:
    expected = bytes.fromhex(hexbytes)
    assert im.read(int(rva, 16), len(expected)) == expected, label
args.output.mkdir(parents=True, exist_ok=True)
ranges = [(0x489D210, 0x489DB8B), (0x488A000, 0x488A97B),
          (0x3564E20, 0x3564EAC), (0x3563AB0, 0x3563B3C),
          (0x3927920, 0x3927A90), (0x4593DD0, 0x4593DD8),
          (0x45964B0, 0x45964BC), (0x30C8E30, 0x30C8E3B),
          (0x3933800, 0x3933878)]  # Native InputModifierNegate::ModifyRaw.
data = {a: im.read(a, b-a) for a, b in ranges}
# Native Negate's +1/-1 constants; keep the exact shipping values.
for rva in (0x870FDE0, 0x6E0BB48):
    data[rva] = im.read(rva, 8)
globals_ = set()
for a, b in ranges[:2]:
    asm = subprocess.check_output(['objdump', '-d', '-Mintel', f'--start-address={im.base+a:#x}',
                                   f'--stop-address={im.base+b:#x}', str(args.exe)], text=True)
    (args.output/f'handler-{a:x}.asm').write_text(asm)
    for address in re.findall(r'# (0x[0-9a-f]+)', asm):
        rva = int(address, 16) - im.base
        if 0x6D00000 <= rva < 0x8F00000:
            data[rva] = im.read(rva, 16)
        if 0x9306200 <= rva < 0x9306400:
            globals_.add(rva)
with (args.output/'shipping-fixture.bin').open('wb') as f:
    f.write(struct.pack('<I', len(data)))
    for rva, value in sorted(data.items()):
        f.write(struct.pack('<II', rva, len(value)))
        f.write(value)
    f.write(struct.pack('<I', len(globals_)))
    for rva in sorted(globals_):
        f.write(struct.pack('<I', rva))
(args.output/'static-validation.json').write_text(json.dumps({
    'sha256': digest, 'signatures': len(signatures),
    'ranges': [[hex(a), hex(b)] for a, b in ranges],
    'note': 'Fixtures retain shipping handlers/modifier runner/add targets; external dependencies are stubbed by tests.'
}, indent=2)+'\n')
print(f'Validated {len(signatures)} prototype signatures and shipping hash; fixture written.')
