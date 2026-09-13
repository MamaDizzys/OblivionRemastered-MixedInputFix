"""Journal compatibility and incomplete-read tests; run with Python directly."""
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from analyze_camera_prototype import analyze


def journal(version=2, committed=True, claimed=1):
    stride = 144 if version == 1 else 304
    data = bytearray(64 + stride * 4096)
    data[:8] = b'MIFCAM01'
    struct.pack_into('<4I2Q', data, 8, version, stride, 4096, 368, claimed, 0x140000000)
    struct.pack_into('<9Q6d6I', data, 64, int(committed), 2, 0x1000, 0x2000, 0x3000,
                     0x4000, 0x5000, 0, 0, *([0.] * 6), 1, 2, 0, 4, 7, 0)
    if version == 2:
        # Independent wire fixture: source_axis, unknown key, unavailable modifiers.
        struct.pack_into('<13Q2I5i7I', data, 64 + 144,
                         0x6000, 0x6050, 0x3000, 999, 0, 0x1234,
                         0x6050, 0x3000, 0x4000, 101, 102, 103, 104,
                         7, 0xfdf, 4, 1, 0, 0, 1, 4, 0, 0, 1, 1, 2, 0)
    return data


class JournalTests(unittest.TestCase):
    def test_original_live_format_remains_readable(self):
        result = analyze(journal(1))
        self.assertEqual(result['version'], 1)
        self.assertEqual(result['records'], 1)
        self.assertEqual(result['first_rejections'], [
            {'reason': 'mappings', 'generation': 2, 'axis': 2, 'axis_name': 'Y'}])
        self.assertEqual(result['verified_pairs'], [])

    def test_inventory_wire_layout_and_read_validity(self):
        result = analyze(journal())
        e = result['first_rejections'][0]['inventory']
        self.assertEqual(e['subreason'], 'source_axis')
        self.assertEqual(e['key'], '0x3e7')
        self.assertEqual(e['mapping'], '0x6050')
        self.assertEqual(e['candidate_instance'], '0x4000')
        self.assertEqual(e['source_name'], 'Unknown')
        self.assertEqual(e['modifier_count'], 0)
        self.assertIsNone(e['modifiers'])
        self.assertNotIn('modifiers', e['readable_fields'])
        self.assertEqual(e['layout_hash_at_rejection'], '0x1234')
        self.assertEqual(e['dispatch']['action'], '0x3000')

    def test_uncommitted_record_is_ignored(self):
        result = analyze(journal(committed=False))
        self.assertEqual(result['records'], 0)
        self.assertEqual(result['first_rejections'], [])

    def test_digital_candidate_subreason(self):
        data = journal()
        struct.pack_into('<I', data, 64 + 144 + 13 * 8, 26)
        e = analyze(data)['first_rejections'][0]['inventory']
        self.assertEqual(e['subreason'], 'digital_candidate')

    def test_saturation_stays_bounded(self):
        result = analyze(journal(claimed=5000))
        self.assertTrue(result['saturated'])
        self.assertEqual(result['records'], 1)

    def test_incomplete_or_incompatible_file_is_rejected(self):
        with self.assertRaises(ValueError):
            analyze(journal()[:-1])
        data = journal()
        struct.pack_into('<I', data, 12, 144)
        with self.assertRaises(ValueError):
            analyze(data)


if __name__ == '__main__':
    unittest.main()
