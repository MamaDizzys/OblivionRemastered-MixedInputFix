"""Synthetic memory tests for the external reader; no game process required."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from camera_key_probe import GUARDS, NEGATE_VTABLE, POOL, Reader, snapshot


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.base = 0x140000000
        self.data = {}
        self.block = 0x200000
        self.owner, self.action, self.mod, self.cls = (0x300000 + i * 0x100 for i in range(4))
        self.maps, self.mods, self.details = 0x400000, 0x500000, 0x600000
        for rva, value in GUARDS.items():
            self.put(self.base + rva, bytes.fromhex(value))
        self.pack(self.base + POOL + 0x10, '<Q', self.block)
        for identity, name in [(0xCD7, 'NumPadEight'), (0xCCA, 'NumPadSix'),
                               (0xBB9, 'MouseX'), (0x100, 'Owner'), (0x120, 'LookUp'),
                               (0x140, 'Negate_0'), (0x160, 'InputModifierNegate')]:
            self.name(identity, name)
        self.pack(self.base + 0x9112A84, '<i', 4)
        self.pack(self.base + 0x9112A70, '<Q', 0x700000)
        self.pack(0x700000, '<Q', 0x710000)
        for i, (ptr, name) in enumerate(zip((self.owner, self.action, self.mod, self.cls), (0x100, 0x120, 0x140, 0x160))):
            self.pack(ptr + 0xC, '<i', i)
            self.pack(ptr + 0x18, '<Q', name)
            self.put(0x710000 + 24 * i, struct.pack('<QIIi', ptr, 0, 0, 0))
        self.pack(self.owner + 0x548, '<Qii', self.maps, 2, 2)
        self.put(self.maps, bytes(0xA0))
        self.pack(self.maps + 0x20, '<QQQ', self.action, 0xCD7, self.details)
        self.pack(self.maps + 0x10, '<Qii', self.mods, 1, 1)
        self.pack(self.maps + 0x70, '<QQQ', self.action, 0xBB9, 0)
        self.pack(self.details, '<Q', 0xCD7)
        self.pack(self.details + 0x42, '<B', 0)
        self.pack(self.mods, '<Q', self.mod)
        self.pack(self.mod + 0x10, '<Q', self.cls)
        self.pack(self.mod, '<Q', self.base + NEGATE_VTABLE)
        self.pack(self.base + NEGATE_VTABLE + 0x2B8, '<Q', self.base + 0x3933800)
        self.put(self.mod + 0x28, b'\x01\x00\x01')
        self.summary = {'pid': 368, 'first_rejections': [{'axis_name': 'Y', 'generation': 1085,
            'inventory': {'mapping_index': 0, 'mapping': hex(self.maps), 'maps': hex(self.maps),
                'count': 2, 'key': '0xcd7', 'dispatch': {'owner': hex(self.owner), 'action': hex(self.action)}}}]}

    def put(self, address, data):
        self.data.update({address + i: b for i, b in enumerate(data)})

    def pack(self, address, fmt, *values):
        self.put(address, struct.pack(fmt, *values))

    def name(self, identity, name):
        self.pack(self.block + 2 * identity, '<H', len(name) << 6)
        self.put(self.block + 2 * identity + 2, name.encode())

    def read(self, address, size):
        try:
            return bytes(self.data[address + i] for i in range(size))
        except KeyError as error:
            raise OSError('Unreadable fixture address') from error

    def reader(self):
        return Reader(self.read, self.base)

    def test_names_mappings_and_exact_negate_fields(self):
        result = snapshot(self.reader(), self.summary)
        rows = result['actions'][0]['mappings']
        self.assertEqual([r['key_name'] for r in rows], ['NumPadEight', 'MouseX'])
        self.assertEqual(rows[0]['key_type'], 0)
        self.assertIsNone(rows[1]['key_type'])
        self.assertEqual(rows[0]['modifiers'][0]['class']['name'], 'InputModifierNegate')
        self.assertEqual(rows[0]['modifiers'][0]['negate'], {'x': True, 'y': False, 'z': True})
        self.assertTrue(result['stable_reread'])

    def test_stale_key_rejected(self):
        self.pack(self.maps + 0x28, '<Q', 0xCCA)
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            snapshot(self.reader(), self.summary)

    def test_unreadable_and_oversized_name_rejected(self):
        with self.assertRaises(OSError):
            self.reader().name(0xFFFF)
        self.pack(self.block + 2 * 0xCD7, '<H', 129 << 6)
        with self.assertRaisesRegex(ValueError, 'length'):
            self.reader().name(0xCD7)

    def test_unknown_modifier_has_no_field_read(self):
        self.pack(self.mod, '<Q', self.base + 0x123456)
        for i in range(3):
            del self.data[self.mod + 0x28 + i]
        result = snapshot(self.reader(), self.summary)
        self.assertNotIn('negate', result['actions'][0]['mappings'][0]['modifiers'][0])

    def test_layout_guard_and_details_mismatch_rejected(self):
        self.pack(self.details, '<Q', 0xCCA)
        with self.assertRaisesRegex(ValueError, 'FKeyDetails identity'):
            snapshot(self.reader(), self.summary)
        self.put(self.base + next(iter(GUARDS)), b'\0')
        with self.assertRaisesRegex(ValueError, 'layout guard'):
            snapshot(self.reader(), self.summary)

    def test_changed_snapshot_rejected(self):
        reader = self.reader()
        reader.name(0xCD7)
        self.name(0xCD7, 'NumPadSeven')
        with self.assertRaisesRegex(ValueError, 'Snapshot changed'):
            reader.verify()

    def test_excessive_modifiers_rejected(self):
        self.pack(self.maps + 0x18, '<ii', 5, 5)
        with self.assertRaisesRegex(ValueError, 'Modifier array'):
            snapshot(self.reader(), self.summary)


if __name__ == '__main__':
    unittest.main()
