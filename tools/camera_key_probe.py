"""Read-only Linux/Proton camera key/modifier snapshot. No debugger or game calls.

Use a journal from the CURRENT game process after exercising both camera axes.
Reads /proc/PID/mem O_RDONLY; rejects stale mapping addresses and changing reads.
Names and metadata are diagnostic evidence, never an eligibility decision.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

from analyze_camera_prototype import analyze

GAME = 'OblivionRemastered-Win64-Shipping.exe'
GAME_HASH = 'b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457'
POOL = 0x906C780
NEGATE_VTABLE = 0x78420D8
# Exact shipping FName resolution and Negate field accesses.
GUARDS = {
    0xF56E7A: '4C 8D 05 FF 58 11 08',
    0xF56EB2: '8D 0C 00 49 03 4C D0 10 0F B7 01 4C 8D 41 02',
    0xF56EC6: 'C1 EA 06 A8 01',
    0x3933800: '48 83 EC 28 80 79 2A 00',
    0x3933836: '80 79 29 00',
    0x3933844: '80 79 28 00',
}


class Reader:
    def __init__(self, read, base):
        self.read, self.base = read, base
        self.samples = {}
        self.total = 0

    def memory(self, address, size):
        if not 0 < address < 2**63 or not 0 < size <= 0x14000:
            raise ValueError('Out-of-bound read request')
        self.total += size
        if self.total > 2**20:
            raise ValueError('Snapshot exceeded 1 MiB read budget')
        data = self.read(address, size)
        if len(data) != size:
            raise ValueError('Incomplete memory read')
        prior = self.samples.setdefault((address, size), data)
        if prior != data:
            raise ValueError('Memory changed while sampling; retry in stable gameplay')
        return data

    def unpack(self, address, fmt):
        return struct.unpack(fmt, self.memory(address, struct.calcsize(fmt)))[0]

    def name(self, identity):
        index, number = identity & 0xffffffff, identity >> 32
        block, offset = index >> 16, 2 * (index & 0xffff)
        if block >= 8192:
            raise ValueError('Invalid FName block')
        ptr = self.unpack(self.base + POOL + 0x10 + 8 * block, '<Q')
        if not ptr:
            raise ValueError('Unallocated FName block')
        header = self.unpack(ptr + offset, '<H')
        length, wide = header >> 6, header & 1
        if not 0 < length <= 128 or offset + 2 + length * (1 + wide) > 0x20000:
            raise ValueError('FName length outside diagnostic bounds')
        data = self.memory(ptr + offset + 2, length * (1 + wide))
        value = data.decode('utf-16-le' if wide else 'ascii')
        if not value.isprintable():
            raise ValueError('Invalid FName text')
        return value + (f'_{number-1}' if number else '')

    def object(self, pointer):
        if not pointer:
            raise ValueError('Null UObject')
        index = self.unpack(pointer + 0xC, '<i')
        count = self.unpack(self.base + 0x9112A84, '<i')
        if not 0 <= index < count:
            raise ValueError('UObject index out of range')
        chunks = self.unpack(self.base + 0x9112A70, '<Q')
        chunk = self.unpack(chunks + 8 * (index >> 16), '<Q')
        item = chunk + 24 * (index & 0xffff)
        actual, flags, _, serial = struct.unpack('<QIIi', self.memory(item, 20))
        # Zero serial is legal for objects never weak-referenced. This reader
        # does not allocate a weak serial or claim lifetime proof from zero.
        if actual != pointer or flags & 0x30200000 or serial < 0:
            raise ValueError('Stale UObject identity')
        return {'pointer': hex(pointer), 'index': index, 'serial': serial,
                'name': self.name(self.unpack(pointer + 0x18, '<Q'))}

    def modifier(self, pointer):
        result = self.object(pointer)
        cls = self.unpack(pointer + 0x10, '<Q')
        result['class'] = self.object(cls)
        vt = self.unpack(pointer, '<Q')
        result['vtable'] = hex(vt)
        # Only inspect class-specific fields for the exact native Negate vtable.
        # Do not interpret arbitrary object bytes or invoke ModifyRaw/ProcessEvent.
        if vt == self.base + NEGATE_VTABLE:
            target = self.unpack(vt + 0x2B8, '<Q')
            if target != self.base + 0x3933800 or result['class']['name'] != 'InputModifierNegate':
                raise ValueError('Negate class/vtable identity mismatch')
            values = self.memory(pointer + 0x28, 3)
            if any(v not in (0, 1) for v in values):
                raise ValueError('Invalid Negate bool fields')
            result['native_modify_raw'] = hex(target)
            result['negate'] = dict(zip(('x', 'y', 'z'), map(bool, values)))
        else:
            result['fields'] = 'Not decoded: native class layout not yet established'
        return result

    def verify(self):
        # Best-effort coherence check, not a stop-the-world or generation snapshot.
        for (address, size), expected in self.samples.items():
            self.total += size
            if self.total > 2**20:
                raise ValueError('Snapshot exceeded 1 MiB read budget')
            if self.read(address, size) != expected:
                raise ValueError('Snapshot changed before verification; retry')


def snapshot(reader, summary):
    for rva, expected in GUARDS.items():
        value = bytes.fromhex(expected)
        if reader.memory(reader.base + rva, len(value)) != value:
            raise ValueError('Shipping diagnostic layout guard mismatch')
    rejections = [r for r in summary['first_rejections'] if r.get('inventory', {}).get('mapping_index', -1) >= 0]
    if not rejections:
        raise ValueError('Journal has no mapping-address evidence')
    result = []
    for rejection in rejections[:50]:
        e = rejection['inventory']
        owner, action = (int(e['dispatch'][k], 16) for k in ('owner', 'action'))
        owner_info, action_info = reader.object(owner), reader.object(action)
        header = reader.memory(owner + 0x548, 16)
        maps, count, capacity = struct.unpack('<Qii', header)
        if not maps or not 0 <= count <= capacity <= 1024:
            raise ValueError('Invalid live mapping array bounds')
        if maps != int(e['maps'], 16) or count != e['count']:
            raise ValueError('Journal mapping inventory is stale; use a fresh journal/process')
        raw = reader.memory(maps, count * 0x50)
        index = e['mapping_index']
        if not 0 <= index < count or int(e['mapping'], 16) != maps + index * 0x50:
            raise ValueError('Journal mapping address/index mismatch')
        observed_action, observed_key = struct.unpack_from('<QQ', raw, index * 0x50 + 0x20)
        if observed_action != action or observed_key != int(e['key'], 16):
            raise ValueError('Journal key/action no longer matches live mapping')
        mappings = []
        for i in range(count):
            m = maps + i * 0x50
            row = raw[i * 0x50:(i + 1) * 0x50]
            if struct.unpack_from('<Q', row, 0x20)[0] != action:
                continue
            if len(mappings) >= 16:
                raise ValueError('More than 16 same-action mappings; diagnostic bound exceeded')
            key, details = struct.unpack_from('<QQ', row, 0x28)
            mods, nmods, modcap = struct.unpack_from('<Qii', row, 0x10)
            if not 0 <= nmods <= modcap <= 64 or nmods > 4 or (nmods and not mods):
                raise ValueError('Modifier array exceeds diagnostic bounds')
            item = {'index': i, 'mapping': hex(m), 'key': hex(key), 'key_name': reader.name(key),
                    'trigger_count': struct.unpack_from('<i', row, 8)[0], 'flags': row[0x40],
                    'details': hex(details), 'modifier_count': nmods, 'modifiers': []}
            if details:
                details_key = reader.unpack(details, '<Q')
                if details_key != key:
                    raise ValueError('FKeyDetails identity mismatch')
                item['key_type'] = reader.unpack(details + 0x42, '<B')
            else:
                item['key_type'] = None  # Never ask the engine to lazily resolve details.
            for j in range(nmods):
                item['modifiers'].append(reader.modifier(reader.unpack(mods + 8 * j, '<Q')))
            mappings.append(item)
        result.append({'axis': rejection['axis_name'], 'journal_generation': rejection['generation'],
                       'owner': owner_info, 'action': action_info, 'count': count, 'mappings': mappings})
    reader.verify()
    return {'journal_pid': summary['pid'], 'game': hex(reader.base), 'actions': result,
            'stable_reread': True, 'sample_bytes': reader.total,
            'note': 'Read-only external snapshot; not synchronized to the journal generation. '
                    'No candidate inactivity or composition eligibility is proven by this snapshot.'}


def locate(pid=None):
    found = []
    processes = [Path(f'/proc/{pid}')] if pid else Path('/proc').glob('[0-9]*')
    for process in processes:
        try:
            lines = (process / 'maps').read_text().splitlines()
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
        for line in lines:
            parts = line.split(maxsplit=5)
            if len(parts) == 6 and parts[5].endswith('/' + GAME) and int(parts[2], 16) == 0:
                found.append((int(process.name), int(parts[0].split('-')[0], 16), Path(parts[5])))
    if len(found) != 1:
        raise ValueError(f'Expected one readable live game mapping; found {len(found)}. '
                         'Run on the host with process-read permission, while the game is running.')
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('journal', type=Path)
    parser.add_argument('--pid', type=int, help='Linux PID, not the Windows journal PID')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    journal_data = args.journal.read_bytes()
    summary = analyze(journal_data)
    pid, base, exe = locate(args.pid)
    if base != int(summary['game'], 16) or hashlib.sha256(exe.read_bytes()).hexdigest() != GAME_HASH:
        raise ValueError('Game base/hash does not match the investigated executable')
    fd = os.open(f'/proc/{pid}/mem', os.O_RDONLY)
    try:
        result = snapshot(Reader(lambda address, size: os.pread(fd, size, address), base), summary)
    finally:
        os.close(fd)
    result['linux_pid'] = pid
    result['journal_sha256'] = hashlib.sha256(journal_data).hexdigest()
    with args.output.open('x') as out:
        json.dump(result, out, indent=2)
        out.write('\n')
    print(args.output)


if __name__ == '__main__':
    main()
