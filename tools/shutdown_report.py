#!/usr/bin/env python3
"""Decode the fixed shutdown journal; no writes to the capture or game."""
import argparse
from pathlib import Path
import re
import struct


def decode(data):
    if len(data) != 8192 or data[:8] != b'MIFEXIT1':
        raise ValueError('Not a complete MIFEXIT1 journal (expected 8192 bytes)')
    version, capacity, pid, count = struct.unpack_from('<IIII', data, 8)
    if version != 1 or capacity != 128:
        raise ValueError('Unsupported journal version/capacity')
    module, game, bridge, installation = struct.unpack_from('<QQQQ', data, 24)
    source = (Path(__file__).resolve().parents[1] / 'src/ShutdownDiagnostic.hpp').read_text()
    enum = re.search(r'enum Event : unsigned\s*\{(.*?)\};', source, re.S)[1]
    names = [word.strip().split(' = ')[0] for word in enum.split(',') if word.strip()]
    rows = []
    for i in range(min(count, capacity)):
        sequence, event, thread, a, b = struct.unpack_from('<IIQQQ', data, 64 + i * 32)
        if sequence != i + 1:
            rows.append(f'{i+1:03} INCOMPLETE SLOT (may be a concurrent read or interrupted recorder)')
            continue
        name = names[event-1] if 1 <= event <= len(names) else f'UNKNOWN_{event}'
        rows.append(f'{sequence:03} tid={thread} {name} a=0x{a:x} b=0x{b:x}')
    return [f'MIFEXIT1 pid={pid} reserved={count}/128',
            f'module=0x{module:x} game=0x{game:x} bridge=0x{bridge:x} installation=0x{installation:x}',
            *rows, *(['OVERFLOW: later events were not retained'] if count > capacity else [])]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('journal', type=Path)
    args = parser.parse_args()
    try:
        print('\n'.join(decode(args.journal.read_bytes())))
    except (OSError, ValueError) as error:
        parser.exit(1, f'{error}\n')
