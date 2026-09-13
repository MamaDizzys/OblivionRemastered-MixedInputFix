"""Offline layout/report checks and optional real GDB hardware execution fixture."""
import argparse
import io
import json
import os
from pathlib import Path
import runpy
import struct
import subprocess
import sys
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]


def offline():
    class Command:
        def __init__(self, *args, **kwargs): pass
    fake = types.SimpleNamespace(Command=Command, Breakpoint=object, COMMAND_USER=0,
                                 write=lambda s: None, selected_thread=lambda: types.SimpleNamespace(ptid=(1, 1, 0)),
                                 post_event=lambda f: f())
    sys.modules['gdb'] = fake
    module = runpy.run_path(str(ROOT / 'tools/camera_view_capture.py'))
    Capture = module['Capture']
    glob = Capture.hit.__globals__
    blob = bytearray(0x10000)
    controller, manager, cvt, mvt, rsp, output = 0x1000, 0x3000, 0x5000, 0x6000, 0x8000, 0x9000
    regs = {'rcx': manager, 'rax': manager + 0x1350, 'rsp': rsp, 'rdi': output, 'rip': 0x357AB0F}
    def mem(address, size):
        if not 0 < address <= address + size <= len(blob):
            raise ValueError('Invalid fixture address')
        return bytes(blob[address:address+size])
    def unpack(address, fmt):
        return struct.unpack('<' + fmt, mem(address, struct.calcsize('<' + fmt)))
    glob.update(memory=mem, unpack=unpack, u64=lambda a: unpack(a, 'Q')[0], reg=regs.__getitem__)
    struct.pack_into('<Q', blob, controller, cvt)
    struct.pack_into('<Q', blob, controller + 0x350, manager)
    struct.pack_into('<Q', blob, manager, mvt)
    struct.pack_into('<Q', blob, rsp + 0x28, 0x12345678)
    struct.pack_into('<ddd', blob, controller + 0x310, 2, 10, 0)
    struct.pack_into('<ddd', blob, manager + 0x1368, 2, 8, 0)
    struct.pack_into('<ddd', blob, output, 2, 8, 0)
    for kind, table in [('controller', cvt), ('manager', mvt)]:
        for slot, target in module['SITES'][kind + '_slots'].items():
            struct.pack_into('<Q', blob, table + int(slot, 16), target)
    assert module['layout'](0, controller) == (cvt, manager, mvt)
    for slot in module['SITES']['manager_slots']:
        address = mvt + int(slot, 16)
        blob[address] ^= 1
        try:
            module['layout'](0, controller)
            raise AssertionError('Accepted an unsupported manager virtual target')
        except ValueError:
            pass
        blob[address] ^= 1
    cap = Capture.__new__(Capture)
    cap.controller, cap.manager, cap.cvt, cap.mvt = controller, manager, cvt, mvt
    cap.rows, cap.breakpoints, cap.label, cap.recording = [], [], 'fixture', True
    cap.ready, cap.end = 0, float('inf')
    cap.file = io.StringIO()
    assert cap.hit() is False
    row = cap.rows[-1]
    assert row['returned_rotation'] == [2, 8, 0] and row['control_rotation'] == [2, 10, 0]
    assert row['caller'] == 0x12345678
    regs['rcx'] = manager + 8
    assert cap.hit() is False and len(cap.rows) == 1
    regs['rcx'] = manager
    # Same caller and cache can stay flat while control advances. Report this
    # observation without declaring a stall or merging a different caller.
    struct.pack_into('<d', blob, controller + 0x318, 11)
    assert cap.hit() is False
    report = runpy.run_path(str(ROOT / 'tools/analyze_camera_view.py'))
    result = report['analyze'](cap.rows)
    assert result['checkpoints'][1]['control_yaw_change'] == 1
    assert result['checkpoints'][1]['view_yaw_change'] == 0
    separate = dict(cap.rows[-1], seq=2, caller=123)
    assert 'previous_seq' not in report['analyze'](cap.rows + [separate])['checkpoints'][-1]
    assert report['angular_difference'](1, 359) == 2
    assert report['angular_difference']('nan', 0) is None
    with tempfile.TemporaryDirectory(prefix='mif-view-report-') as temp:
        p = Path(temp) / 'trace.jsonl'
        p.write_text(''.join(json.dumps(r) + '\n' for r in cap.rows))
        assert '2/2' in report['report'](p)
        assert p.with_suffix('.views.csv').exists()
    # A stale object must stop rather than silently accepting the saved pointer.
    struct.pack_into('<Q', blob, controller + 0x350, manager + 8)
    assert cap.hit() is True and cap.rows[-2]['event'] == 'capture_error'
    assert cap.rows[-1]['reason'] == 'read_or_layout_error'
    relocated, image_bytes = 0x180000000, {}
    checks = [(s['rva'], s['bytes']) for s in module['SITES']['sites'].values()]
    checks += [(int(r, 16), s) for r, s in module['SITES']['guards'].items()]
    for rva, signature in checks:
        image_bytes.update({relocated + rva + i: b for i, b in enumerate(bytes.fromhex(signature))})
    glob['memory'] = lambda a, n: bytes(image_bytes[a+i] for i in range(n))
    glob['camera'].Capture.validate = lambda self: None
    module['validate'](relocated)
    for rva, _ in checks:
        image_bytes[relocated+rva] ^= 1
        try:
            module['validate'](relocated)
            raise AssertionError('Accepted corrupt view bytes')
        except ValueError:
            pass
        image_bytes[relocated+rva] ^= 1
    # Export a binding from a selected process without arming a trial. It must
    # identify the process incarnation, not just retain its reusable PID.
    glob['SELECTED'] = (os.getpid(), relocated, controller, cvt, manager, mvt)
    glob['validate'] = lambda base: None
    glob['layout'] = lambda base, obj: (cvt, manager, mvt)
    fake.selected_inferior = lambda: types.SimpleNamespace(pid=os.getpid())
    messages = []
    fake.write = messages.append
    module['Export']().invoke('', False)
    binding_path = Path(messages[-1].splitlines()[0])
    try:
        binding = json.loads(binding_path.read_text())
        assert binding['event'] == 'view_binding' and binding['version'] == 1
        assert binding['pid'] == os.getpid() and binding['controller'] == controller
        stat = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
        assert binding['start_ticks'] == int(stat[19])
        assert binding['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    finally:
        binding_path.unlink()
    print('PASS view decoder, identity/layout rejection, same-caller report, relocated byte guards')
    print('PASS one-time binding export with process start and boot identity; no trial')


def hardware():
    with tempfile.TemporaryDirectory(prefix='mif-view-gdb-') as temp:
        work = Path(temp)
        (work/'fixture.c').write_text('''
#include <stdint.h>
#include <pthread.h>
unsigned char controller[0x600], manager[0x1400];
uintptr_t manager_vtable[0x900/8];
double location[3], rotation[3];
extern void __attribute__((ms_abi)) get_view(void *, double *, double *);
extern void leaf(void);
__attribute__((noinline)) void marker(void) { __asm__ volatile("nop"); }
void *worker(void *unused) {
    *(double *)(controller + 0x318) = 11;
    get_view(manager, location, rotation);
    return 0;
}
int main(void) {
    *(uintptr_t *)manager = (uintptr_t)manager_vtable;
    manager_vtable[0x750/8] = (uintptr_t)leaf;
    *(uintptr_t *)(controller + 0x350) = (uintptr_t)manager;
    *(double *)(controller + 0x318) = 10;
    *(double *)(manager + 0x1370) = 8;
    marker();
    get_view(manager, location, rotation);
    pthread_t thread;
    pthread_create(&thread, 0, worker, 0);
    pthread_join(thread, 0);
    marker();
    return rotation[1] != 8;
}
''')
        # Exact shipping getter instruction sequence through the checkpoint;
        # the virtual leaf preserves RCX and returns manager+0x1350.
        sites = json.loads((ROOT/'tools/camera_view_sites.json').read_text())
        getter = bytes.fromhex(sites['guards']['0x357aad0'])
        leaf = bytes.fromhex(sites['guards']['0x357aa60'])
        def directive(data): return '.byte ' + ','.join(hex(b) for b in data)
        (work/'fixture.S').write_text('.text\n.globl get_view, leaf, view_checkpoint\nget_view:\n' +
            directive(getter[:0x3F]) + '\nview_checkpoint:\n' + directive(getter[0x3F:]) +
            '\nleaf:\n' + directive(leaf) + '\n.section .note.GNU-stack,"",@progbits\n')
        subprocess.run(['cc', '-g', '-O0', '-pthread', str(work/'fixture.c'), str(work/'fixture.S'),
                        '-o', str(work/'fixture')], check=True)
        script = work/'check.gdb'
        script.write_text(f'''set pagination off
set confirm off
set debuginfod enabled off
break marker
run
source {ROOT / 'tools/camera_view_capture.py'}
python
import io
cap = Capture.__new__(Capture)
cap.controller = int(gdb.parse_and_eval('&controller[0]'))
cap.manager = int(gdb.parse_and_eval('&manager[0]'))
cap.cvt = 0
cap.mvt = int(gdb.parse_and_eval('&manager_vtable[0]'))
cap.rows = []
cap.label = 'native-fixture'
cap.recording = True
cap.ready = 0
cap.end = float('inf')
cap.file = io.StringIO()
cap.breakpoints = [Probe(cap, int(gdb.parse_and_eval('&view_checkpoint')))]
assert cap.breakpoints[0].type == gdb.BP_HARDWARE_BREAKPOINT
end
continue
python
assert len(cap.rows) == 2, cap.rows
assert [r['control_rotation'][1] for r in cap.rows] == [10, 11], cap.rows
assert all(r['returned_rotation'] == r['cache_rotation'] == [0, 8, 0] for r in cap.rows), cap.rows
assert len(set(r['thread'] for r in cap.rows)) == 2, cap.rows
for row, caller in zip(cap.rows, ('main', 'worker')):
    assert gdb.execute('info symbol %#x' % row['caller'], to_string=True).startswith(caller + ' + '), row
cap.finish('fixture_complete')
assert len(gdb.breakpoints()) == 1
print('PASS real hardware execution checkpoint, shipping getter bytes, returned output, caller stack, new thread, cleanup')
end
continue
''')
        result = subprocess.run(['gdb', '-q', '-nx', '-batch', '-x', str(script), str(work/'fixture')],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(result.stdout)
        if result.returncode or 'PASS real hardware execution checkpoint' not in result.stdout:
            raise RuntimeError('Hardware view checkpoint fixture failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gdb', action='store_true')
    args = parser.parse_args()
    offline()
    if args.gdb:
        hardware()
