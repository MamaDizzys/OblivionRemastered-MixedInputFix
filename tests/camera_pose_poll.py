"""Pose polling decoder tests and a running child-process read, without GDB."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools'))
import camera_pose_poll as poll
from analyze_camera_pose_poll import analyze, report


def offline():
    controller, manager = 0x1000, 0x3000
    blob = bytearray(0x5000)
    struct.pack_into('<Q', blob, controller+0x350, manager)
    struct.pack_into('<3d', blob, controller+0x310, 0, 359, 0)
    struct.pack_into('<f', blob, manager+0x1340, 4)
    struct.pack_into('<3d', blob, manager+0x1368, 0, 350, 0)
    source = {'controller': controller, 'manager': manager}
    def read(a, n): return bytes(blob[a:a+n])
    identities = [poll.object_identity(read, controller), poll.object_identity(read, manager)]
    first = poll.snapshot(read, source, identities)
    assert first['repeated_bytes_equal']
    assert first['after']['control_rotation'] == [0, 359, 0]
    assert first['after']['cache_rotation'] == [0, 350, 0]
    assert first['after']['cache_stamp'] == 4
    # Validate relocated code and both virtual tables before accepting pointers.
    base, cvt, mvt = 0x180000000, 0x7000, 0x8000
    data = {}
    for site in poll.SITES['sites'].values():
        data.update({base+site['rva']+i: b for i, b in enumerate(bytes.fromhex(site['bytes']))})
    for rva, signature in poll.SITES['guards'].items():
        data.update({base+int(rva, 16)+i: b for i, b in enumerate(bytes.fromhex(signature))})
    for kind, obj, vt in [('controller', controller, cvt), ('manager', manager, mvt)]:
        struct.pack_into('<Q', blob, obj, vt)
        for slot, target in poll.SITES[kind+'_slots'].items():
            data.update({vt+int(slot, 16)+i: b for i, b in enumerate(struct.pack('<Q', base+target))})
    def mapped(a, n):
        return read(a, n) if a < len(blob) else bytes(data[a+i] for i in range(n))
    full = dict(source, game_base=base, controller_vtable=cvt, manager_vtable=mvt)
    identities = poll.validate(mapped, full)
    address = mvt + 0x750
    data[address] ^= 1
    try:
        poll.validate(mapped, full)
        raise AssertionError('Accepted unsupported cache accessor')
    except ValueError:
        pass
    data[address] ^= 1
    calls = 0
    def changing(a, n):
        nonlocal calls
        if a == manager+0x1340:
            calls += 1
            struct.pack_into('<d', blob, manager+0x1370, 350+calls)
        return read(a, n)
    second = poll.snapshot(changing, source, identities)
    assert not second['repeated_bytes_equal']
    assert second['before']['cache_rotation'][1] == 351
    assert second['after']['cache_rotation'][1] == 352
    struct.pack_into('<d', blob, controller+0x318, 1)
    third = poll.snapshot(read, source, identities)
    rows = [dict(r, seq=i, host_time=i*.05, skipped_deadlines=0) for i, r in enumerate((first, second, third))]
    summary = analyze(rows)
    assert summary['repeated_reads_equal'] == 2
    assert all('previous_seq' not in p for p in summary['checkpoints'])  # No bridging an unstable poll.
    steady = [rows[0], rows[2]]
    assert analyze(steady)['checkpoints'][1]['control_yaw_change'] == 2
    struct.pack_into('<Q', blob, controller+0x350, manager+8)
    try:
        poll.snapshot(read, source, identities)
        raise AssertionError('Accepted changed object binding')
    except ValueError:
        pass
    with tempfile.TemporaryDirectory() as directory:
        p = Path(directory)/'trace.jsonl'
        p.write_text(''.join(json.dumps(r)+'\n' for r in rows))
        assert 'Samples: 3' in report(p)
        binding = dict(full, event='view_binding', version=1, **poll.process_identity(os.getpid()),
                       host_time=time.monotonic(), game_sha256=poll.SITES['game_sha256'])
        for key, bad in [('start_ticks', binding['start_ticks']+1), ('boot_id', 'other-boot')]:
            p.write_text(json.dumps(dict(binding, **{key: bad}))+'\n')
            try:
                poll.run(types.SimpleNamespace(source=p))
                raise AssertionError('Accepted binding from another process incarnation')
            except ValueError as error:
                assert 'incarnation' in str(error)
    print('PASS asynchronous decode, changing-read retention, stale binding rejection, report gaps and yaw wrap')


def child_memory():
    program = '''
import ctypes,json,os,struct,sys
c=ctypes.create_string_buffer(0x600);m=ctypes.create_string_buffer(0x1400)
ca,ma=ctypes.addressof(c),ctypes.addressof(m)
ctypes.memmove(ca+0x350,struct.pack('<Q',ma),8)
ctypes.memmove(ca+0x318,struct.pack('<d',10),8)
ctypes.memmove(ma+0x1370,struct.pack('<d',8),8)
print(json.dumps({'pid':os.getpid(),'controller':ca,'manager':ma}),flush=True)
sys.stdin.readline()
ctypes.memmove(ca+0x318,struct.pack('<d',11),8)
print('advanced',flush=True)
sys.stdin.readline()
'''
    child = subprocess.Popen([sys.executable, '-c', program], text=True,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        source = json.loads(child.stdout.readline())
        identity = poll.process_identity(child.pid)
        memory = poll.Memory(child.pid)
        try:
            ids = [poll.object_identity(memory.read, source[k]) for k in ('controller', 'manager')]
            one = poll.snapshot(memory.read, source, ids)
            child.stdin.write('advance\n'); child.stdin.flush()
            assert child.stdout.readline().strip() == 'advanced'
            two = poll.snapshot(memory.read, source, ids)
            assert one['after']['control_rotation'][1] == 10
            assert two['after']['control_rotation'][1] == 11
            assert one['after']['cache_rotation'][1] == two['after']['cache_rotation'][1] == 8
            assert poll.process_identity(child.pid) == identity
        finally:
            memory.close()
    finally:
        child.stdin.close()
        child.wait(timeout=5)
    print('PASS read-only /proc memory sampling while an untraced child advances, process identity unchanged')


if __name__ == '__main__':
    offline()
    child_memory()
