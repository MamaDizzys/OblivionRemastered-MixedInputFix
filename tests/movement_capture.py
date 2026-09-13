"""Exercise the observing code with synthetic memory; no live findings implied."""
from pathlib import Path
import runpy
import struct
import sys
import types

root = Path(__file__).resolve().parents[1]
class Command:
    def __init__(self, *args): pass
sys.modules['gdb'] = types.SimpleNamespace(Command=Command, Breakpoint=object,
    COMMAND_USER=0, write=lambda _: None,
    selected_thread=lambda: types.SimpleNamespace(ptid=(1, 2, 3)))
module = runpy.run_path(str(root / 'tools/movement_capture.py'))
Capture = module['Capture']
env = Capture.hit.__globals__
blob = bytearray(0x20000)
registers = dict(rsp=0x1F000, rbp=0x16000, r13=0x1000, rcx=0, rdx=0,
                 rdi=0, r14=0x1000, rbx=0, rax=0)
vectors = {}
env['reg'] = registers.__getitem__
env['xmm'] = lambda n, kind='float': vectors.get((n, kind), 0.)
def memory(address, size):
    if address <= 0 or address + size > len(blob): raise ValueError('invalid read')
    return bytes(blob[address:address + size])
env['memory'] = memory
def put(address, fmt, *args): struct.pack_into('<' + fmt, blob, address, *args)
def val(address, x): put(address, 'dddB', x, 0., 0., 1)
cap = Capture.__new__(Capture)
cap.base, cap.limit, cap.count, cap.recording = 0, 1000, 0, True
cap.threads, rows = {}, []
def write(row):
    row['seq'] = cap.count
    cap.count += 1
    rows.append(row)
cap.write = write
cap.request_finish = lambda reason: setattr(cap, 'reason', reason)
def hit(name):
    assert not cap.hit(name), rows[-1]
    return rows[-1]
vectors[2, 'float'] = .016
assert hit('reset')['delta'] == .016
instance, action, binding, vtable, obj, input_value = 0x4000, 0x5000, 0x6000, 0x7000, 0x8000, 0xA000
put(instance, 'Q', action); put(action + 0x51, 'B', 0); val(instance + 0x38, 1.)
put(binding, 'Q', vtable); put(vtable + 8, 'Q', 0xDEAD)
registers.update(rcx=binding, rdx=instance)
dispatch = hit('dispatch_begin')['dispatch_id']
registers.update(rsp=0x1E000, rcx=obj, rdx=input_value)
put(registers['rsp'], 'Q', 0xBEEF); val(input_value, 1.)
put(obj + 0xD4C, 'ffff', 0., -1., 0., 0.)
row = hit('backward_entry')
assert row['dispatch_id'] == dispatch and row['input']['xyz'][0] == 1.
assert row['caches']['backward'] == -1.
registers.update(rbx=obj, rcx=0xB000, rax=0)
put(0xB091, 'B', 0); vectors[6, 'float'] = 1.
hit('backward_getter')
registers['rcx'] = 0xDEAD  # Redirected C++ getter can clobber RCX.
row = hit('backward_branch')
assert row['raw_float'] == 1. and row['global_input_type'] == 0 and row['common_input'] == 0xB000
put(obj + 0xD50, 'f', 0.)
assert hit('backward_post')['caches']['backward'] == 0.
registers['rdi'] = obj
vectors[2, 'double'], vectors[3, 'double'] = -.4, .25
row = hit('consume_sum')
assert (row['forward_sum'], row['right_sum']) == (-.4, .25)
# A nested reset invalidates observer generation but retains the enclosing
# dispatch identity so the capture exposes that relationship rather than hiding it.
registers.update(rbp=0x15000, rsp=0x1D000)
assert hit('reset')['observed_generation'] == 2
registers.update(rsp=0x1F000, rbp=0x16000)
assert hit('dispatch_end')['dispatch_id'] == dispatch
# Exercise actual mapping stack offsets and full eight-byte key identities.
env['KEYS'] = {'Gamepad_LeftX': 0xC000, 'Gamepad_LeftY': 0xC010}
put(0xC000, 'Q', 0x100000007); put(0xC010, 'Q', 0x200000007)
put(0xC020, 'Q', 0x100000007)
frame = 0x14000
put(frame + 0x1F, 'Q', 0xC020); put(frame + 0x37, 'Q', 0x15000)
put(frame + 0x3F, 'Q', 0x392BCBF); put(frame + 0x67, 'Q', input_value)
registers.update(rbp=frame, rdi=instance, rcx=0)
val(input_value, -.7)
assert hit('mapping_input')['key'] == 'Gamepad_LeftX'
put(frame - 0x49, 'd', -.7); put(frame - 0x69, 'd', 1.)
row = hit('merge_before')
assert (row['candidate'], row['accumulated']) == (-.7, 1.)
# Unknown is not silently promoted to keyboard/digital.
put(0xC020, 'Q', 999)
assert hit('merge_after')['key'] == 'Other'
registers['rcx'] = 3
assert cap.hit('merge_before') and cap.reason == 'read_error'
assert rows[-1]['event'] == 'capture_error'
print('PASS: movement values/caches, dispatch correlation, reset generations, mapping identity/offsets, sums, fail-stop reads')

# Delayed sparse mode records whole reset-to-reset windows, with a hard timeout
# and the existing event limit. No game execution is needed for these checks.
cap.threads, cap.count, rows = {}, 0, []
cap.timing = {'ready': float('inf'), 'end': None}
cap.arm_on_hit = True
clock = [0.]
env['time'] = types.SimpleNamespace(monotonic=lambda: clock[0])
registers.update(rsp=0x1F000, rbp=0x16000, r13=0x1000, rcx=0)
assert not cap.hit('reset') and not rows
clock[0] = 7.9
assert not cap.hit('reset') and not rows
clock[0] = 8.
assert hit('reset')['observed_generation'] == 1
clock[0] = 8.1
assert not cap.hit('reset')
assert rows[-1]['event'] == 'window_end' and rows[-1]['same_identity']
count = cap.count
registers['rdi'] = obj
assert not cap.hit('consume_sum') and cap.count == count
clock[0] = 9.
assert hit('reset')['observed_generation'] == 3
clock[0] = 11.
assert cap.hit('reset') and cap.reason == 'timed_complete'
assert rows[-1]['event'] == 'window_end'
cap.timing = {'ready': 0., 'end': None}
clock[0] = 5.
assert cap.hit('consume_sum') and cap.reason == 'timed_partial'
print('PASS: 8-second preparation, sparse complete windows, timed stop, no-reset timeout')

# Summary keeps ordered provenance and final handler values, flags incomplete
# traces and read errors, and bounds pasted output separately from raw evidence.
from tempfile import TemporaryDirectory
summary = runpy.run_path(str(root / 'tools/movement_summary.py'))['report']
sample = []
def add(event, **kwargs):
    r = dict(event=event, seq=len(sample), thread='t', observed_generation=1,
             owner=0x1000, evaluation_frame=0x16000)
    r.update(kwargs); sample.append(r)
def vv(v): return {'xyz': [v, 0., 0.], 'type': 1}
add('reset')
add('mapping_input', action=action, instance=instance, mapping_frame=frame,
    key='Other', key_identity=7, mapping_input=vv(1.), caller=0x392BCBF, saved_evaluation_frame=0x16000)
add('merge_before', action=action, instance=instance, mapping_frame=frame,
    key='Other', key_identity=7, component=0, policy=0, candidate=1., accumulated=-.7)
add('merge_after', action=action, instance=instance, mapping_frame=frame,
    key='Other', key_identity=7, component=0, policy=0, candidate=1., accumulated=1.)
add('dispatch_begin', dispatch_id=4, action=action, instance=instance, binding=binding, value=vv(1.))
add('backward_entry', direction='backward', object=obj, dispatch_id=4,
    input=vv(1.), caches={'forward': 0., 'backward': -1., 'left': 0., 'right': 0.})
add('backward_post', direction='backward', object=obj, dispatch_id=4,
    caches={'forward': 0., 'backward': 0., 'left': 0., 'right': 0.})
add('window_end', same_identity=True)
sample.append(dict(event='capture_end', reason='timed_complete'))
import json
with TemporaryDirectory() as tmp:
    path = Path(tmp) / 'trace.jsonl'
    path.write_text(''.join(json.dumps(r) + '\n' for r in sample))
    text = summary(path)
    assert 'key=Other/0x7' in text and 'acc=-0.7->1' in text and 'complete=True' in text
    assert text.index('MAP ') < text.index('MERGE ') < text.index('DISPATCH_BEGIN ')
    assert 'backward_post' in text and len(text.splitlines()) <= 150
    sample = sample[:-2] + [dict(event='capture_error', site='probe', error='bad read')]
    path.write_text(''.join(json.dumps(r) + '\n' for r in sample))
    text = summary(path)
    assert 'OPEN/PARTIAL' in text and 'complete=False' in text and 'ERROR probe: bad read' in text
print('PASS: compact report mapping order, merge values, dispatch linkage, completeness/error flags')

# Model GDB source without __file__, including an unrelated pre-existing value.
# Resolve both companions from the code filename while CWD points elsewhere.
import os
source = root / 'tools/movement_capture.py'
original_cwd = Path.cwd()
try:
    os.chdir('/tmp')
    for initial in ({}, {'__file__': '/tmp/unrelated.py'}):
        exec(compile(source.read_text(), str(source), 'exec'), initial)
        assert initial['TOOL_DIRECTORY'] == source.parent
        assert initial['MANIFEST']['sites']['backward_branch']['rva'] == 0x488AC41
finally:
    os.chdir(original_cwd)
for original in (b'\x3c\x01\x90\x90\x0f', b'\x3c\x01\x75\x0f\x0f'):
    env['memory'] = lambda address, size: original[:size]
    assert env['site_matches'](0, 'backward_branch', {'rva': 1, 'bytes': '3c0190900f'})
env['memory'] = lambda address, size: b'\x3c\x01\xeb\x0f\x0f'[:size]
assert not env['site_matches'](0, 'backward_branch', {'rva': 1, 'bytes': '3c0190900f'})
print('PASS: GDB source path without __file__, stale __file__/foreign CWD, original/NOP branches and rejection of unexpected branch')
