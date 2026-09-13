#!/usr/bin/env python3
"""Read-only check of every production signature against an on-disk PE image."""
import argparse
import hashlib
from pathlib import Path
import re
import struct
parser = argparse.ArgumentParser()
parser.add_argument('exe', type=Path)
args = parser.parse_args()
data = args.exe.read_bytes()
pe, = struct.unpack_from('<I', data, 0x3c)
sections, = struct.unpack_from('<H', data, pe + 6)
optional_size, = struct.unpack_from('<H', data, pe + 20)
assert data[:2] == b'MZ' and data[pe:pe+4] == b'PE\0\0'
root = Path(__file__).resolve().parents[1]
source = '\n'.join((root / name).read_text() for name in ('src/Sites.hpp', 'src/CameraSites.hpp'))
names = {name: int(value, 16) for name, value in re.findall(r'uintptr_t (\w+) = (0x[\dA-Fa-f]+);', source)}
def extract(rva, size):
    for i in range(sections):
        header = pe + 24 + optional_size + i * 40
        virtual_size, start, raw_size, offset = struct.unpack_from('<4I', data, header + 8)
        if start <= rva and rva + size <= start + raw_size:
            return data[offset + rva - start:offset + rva - start + size]
    raise ValueError(f'RVA outside raw section: {rva:x}')
count = 0
for address, hex_bytes, label in re.findall(r'\{(\w+), "([\dA-F ]+)", "([^"]+)"\}', source):
    rva = names[address] if address in names else int(address, 16)
    expected = bytes.fromhex(hex_bytes)
    actual = extract(rva, len(expected))
    assert actual == expected, f'{label}: {actual.hex(" ")} != {expected.hex(" ")}'
    print(f'PASS 0x{rva:08X} {label}: {expected.hex(" ").upper()}')
    count += 1
print(f'{count} signatures matched; SHA256 {hashlib.sha256(data).hexdigest()}')
