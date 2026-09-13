"""Offline regressions for shutdown observer address/return/event handling."""
import io
from pathlib import Path
import runpy
import struct
import sys
import types

class Command:
    def __init__(self, *args): pass

class Breakpoint:
    def __init__(self, address, internal):
        self.address, self.enabled = address, True

blob = bytearray(0x10000)
registers = dict(rsp=0x5000, rax=1)
thread = types.SimpleNamespace(ptid=(1, 2, 3))
inferior = types.SimpleNamespace(read_memory=lambda a, n: blob[a:a+n])
gdb = types.SimpleNamespace(Command=Command, Breakpoint=Breakpoint, COMMAND_USER=0,
                            selected_inferior=lambda: inferior, selected_thread=lambda: thread,
                            parse_and_eval=lambda name: registers[name[1:]], write=lambda text: None)
sys.modules['gdb'] = gdb
module = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'tools/shutdown_capture.py'))

def put(address, value): struct.pack_into('<I', blob, address, value)

pe, base = 0x1100, 0x1000
put(pe + 136, 0x200)
put(pe + 140, 0x100)
for offset, value in [(20, 1), (24, 1), (28, 0x300), (32, 0x310), (36, 0x320)]:
    put(base + 0x200 + offset, value)
put(base + 0x300, 0x1000)
put(base + 0x310, 0x400)
blob[base+0x400:base+0x40E] = b'uninstall_mod\0'
loaded = dict(base=base, pe=pe)
assert module['export'](loaded, 'uninstall_mod') == 0x2000
put(base + 0x300, 0x220)
try:
    module['export'](loaded, 'uninstall_mod')
    raise AssertionError('forwarded export accepted')
except ValueError: pass

events = []
cap = types.SimpleNamespace(emit=lambda name, **kw: events.append((name, kw)) or False)
struct.pack_into('<Q', blob, registers['rsp'], 0x9876)
probe = module['ReturnProbe'](cap, 'uninstall')
assert probe.address == '*0x9876'
assert not probe.stop() and not events  # Entry RSP is not the actual return.
registers['rsp'] += 8
thread.ptid = (1, 9, 3)
assert not probe.stop() and not events  # Another thread at the same return site.
thread.ptid = (1, 2, 3)
assert not probe.stop() and events == [('uninstall_return', {'rax': 1})]
assert not probe.enabled
cap = module['Capture'].__new__(module['Capture'])
cap.file, cap.count, cap.probes = io.StringIO(), 31, [types.SimpleNamespace(enabled=True)]
assert cap.emit('last') and cap.count == 32 and not cap.probes[0].enabled
assert cap.emit('overflow') and cap.count == 32 and cap.file.getvalue().count('\n') == 1
print('PASS: PE export/forward rejection, exact return thread/RSP, bounded shutdown events')
