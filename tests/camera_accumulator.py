"""Synthetic decoder/pairing tests; --gdb also exercises a real hardware watchpoint.

No game process, installed DLL, or production source is changed.
"""
import argparse
import importlib.util
import io
import json
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
                                 write=lambda s: None)
    sys.modules['gdb'] = fake
    module = runpy.run_path(str(ROOT / 'tools/camera_accumulator_capture.py'))
    Capture = module['Capture']
    glob = Capture.hit.__globals__
    blob = bytearray(0x10000)
    obj, rsp = 0x1000, 0x8000
    regs = {'rsp': rsp, 'rip': 0, 'rbx': obj, 'rsi': obj, 'rdi': obj,
            'rcx': obj, 'rdx': 0x5000, 'rax': 0}
    def mem(address, size):
        if not 0 < address <= address + size <= len(blob):
            raise ValueError('invalid synthetic memory')
        return bytes(blob[address:address+size])
    def unpack(address, fmt):
        return struct.unpack('<'+fmt, mem(address, struct.calcsize('<'+fmt)))
    glob.update(memory=mem, unpack=unpack, u64=lambda p: unpack(p, 'Q')[0],
                reg=regs.__getitem__, double_register=lambda r: {'xmm0': 0.25, 'xmm3': -2., 'xmm10': 0.}[r])
    fake.selected_thread = lambda: types.SimpleNamespace(ptid=(1, 1, 0))
    fake.post_event = lambda f: f()
    fake.execute = lambda *args, **kwargs: 'synthetic backtrace'
    fake.parse_and_eval = lambda expression: 0.25
    cap = Capture.__new__(Capture)
    cap.obj, cap.vtable, cap.base, cap.label = obj, 0, 0, 'synthetic'
    cap.recording, cap.sampling, cap.ready, cap.end = True, True, 0, float('inf')
    cap.count, cap.file, cap.breakpoints = 0, io.StringIO(), []
    cap.adds, cap.consumers, cap.setters, cap.signs = {}, {}, {}, {}
    cap.last_bits, cap.last_value = bytes(8), 0.
    def event(name):
        if name != 'write':
            regs['rip'] = module['SITES']['sites'][name]['rva']
        assert cap.hit(name) is False
    def rows(): return [json.loads(s) for s in cap.file.getvalue().splitlines()]
    struct.pack_into('<Q', blob, rsp+0x38, 0x489DB0B)
    event('add')
    struct.pack_into('<d', blob, obj+0x530, 0.25)
    regs['rip'] = 0x3564EA6
    event('write')
    assert rows()[-1]['add_id'] == 0 and rows()[-1]['caller_kind'] == 'x_mouse_handler'
    assert rows()[-1]['before'] == 0 and rows()[-1]['after'] == 0.25
    event('consume')
    struct.pack_into('<ddd', blob, rsp+0x48, 0., 0.25, 0.)
    struct.pack_into('<ddd', blob, rsp+0x30, 0., 10., 0.)
    event('manager_after')  # Includes null-manager path; not falsely called "processed".
    assert rows()[-1]['consumer_id'] == 2 and rows()[-1]['local_delta'][1] == 0.25
    # Setter's original RCX is clobbered at return. Saved RBX and exact stack
    # depth must pair the result without reading volatile argument registers.
    regs['rsp'] = rsp - 8
    struct.pack_into('<Q', blob, rsp-8, 0x359B4E6)
    struct.pack_into('<ddd', blob, 0x5000, 0., 10.25, 0.)
    event('set_enter')
    regs['rsp'], regs['rcx'] = rsp - 8 - 0xB8, 0xDEAD
    struct.pack_into('<ddd', blob, obj+0x310, 0., 10.25, 0.)
    event('set_return')
    assert rows()[-1]['set_id'] == 4 and rows()[4]['consumer_id'] == 2
    regs['rsp'], regs['rcx'] = rsp, obj
    event('sign_test'); event('sign_skip')
    assert rows()[-1]['sign_id'] == 6 and rows()[-1]['computed_yaw_delta'] == -2
    # A vector clear updates yaw; watchpoint PC is after the vector store.
    struct.pack_into('<dd', blob, obj+0x528, 0., 0.)
    regs['rip'] = 0x35970B7
    event('write')
    assert rows()[-1]['writer'] == 'tick_tail_clear' and rows()[-1]['before'] == 0.25
    # Unseen writer is retained, not classified as normal accumulation.
    regs.update(rip=0x1234, r8=0, r9=0, r10=0, r11=0)
    struct.pack_into('<d', blob, obj+0x530, -0.5)
    event('write')
    assert rows()[-1]['writer'] == 'unknown' and 'backtrace' in rows()[-1]
    # Other receivers do not contaminate the one-object trace.
    n = cap.count
    regs['rbx'] = obj+8
    event('add')
    assert cap.count == n
    regs['rbx'] = obj
    # Consumer-slot validation prevents accepting the alternate controller
    # consumer while silently observing only the normal one.
    original_u64 = glob['u64']
    vtable = 0x200
    slots = {obj: vtable, vtable+0xD18: 0x3564E20, vtable+0x760: 0x30BACE0,
             vtable+0x768: 0x30D1C90, vtable+0xC00: 0x359B340}
    glob['u64'] = slots.__getitem__
    assert module['receiver_layout'](0, obj) == vtable
    slots[vtable+0xC00] = 0x3114840
    try:
        module['receiver_layout'](0, obj)
        raise AssertionError('Accepted unsupported alternate consumer')
    except ValueError:
        pass
    glob['u64'] = original_u64
    # Source path is resilient to GDB's absent/foreign __file__ behavior.
    source = (ROOT/'tools/camera_accumulator_capture.py').read_text()
    for namespace in ({'__name__': '__test__'}, {'__file__': '/tmp/foreign.py'}):
        exec(compile(source, str(ROOT/'tools/camera_accumulator_capture.py'), 'exec'), namespace)
        assert namespace['DIRECTORY'] == ROOT/'tools'
    spec = importlib.util.spec_from_file_location('report', ROOT/'tools/analyze_camera_accumulator.py')
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    result = report.analyze(rows())
    assert len(result['setter_results']) == 1
    assert result['setter_results'][0]['request_error_wrapped'] == 0
    assert result['changed_writers']['unknown'] == 1
    assert not result['ended']
    assert report.angular_difference(1, 359) == 2
    assert report.angular_difference('nan', 0) is None
    bad = rows()
    bad[5]['thread'] = 'other'
    assert report.analyze(bad)['setter_results'] == []
    # A complete consumer chain must keep call/stack identity. A small declined
    # setter request remains an observed discrepancy, not a missing pair.
    names = ['add', 'write', 'history_copy', 'consume', 'manager_before',
             'manager_after', 'set_enter', 'set_return', 'write']
    cycle = [dict(seq=i, event=name, thread='t', receiver=obj, rsp=rsp,
                  accumulator=[0., .25, 0.], control_rotation=[0., 10., 0.])
             for i, name in enumerate(names)]
    cycle[0].update(caller=123, caller_kind='x_mouse_handler')
    cycle[1].update(writer='native_add', add_id=0, caller=123, after=.25)
    cycle[2]['copy_yaw'] = .25
    for r in cycle[3:7]: r['consumer_id'] = 3
    cycle[4].update(local_delta=[0., .25, 0.], view_rotation=[0., 10., 0.])
    cycle[5].update(local_delta=[0., 0., 0.], view_rotation=[0., 10.25, 0.])
    cycle[6].update(rsp=rsp-8, requested_rotation=[0., 10.25, 0.])
    cycle[7].update(rsp=rsp-8-0xB8, set_id=6, control_rotation=[0., 10.25, 0.])
    cycle[8].update(writer='tick_tail_clear', before=.25, after=0.)
    assert report.consumer_sequences(cycle)['complete'] == 1
    assert all(report.consumer_sequences(cycle)['results'][0]['checks'].values())
    assert report.intervening_cycles(cycle)['exact_contiguous_cycles'] == 1
    cycle[7]['control_rotation'] = [0., 10., 0.]
    assert report.consumer_sequences(cycle)['complete'] == 1
    assert not report.consumer_sequences(cycle)['results'][0]['checks']['returned_rotation_equals_request']
    cycle[7]['rsp'] += 8
    assert report.consumer_sequences(cycle)['complete'] == 0
    assert report.intervening_cycles(cycle)['exact_contiguous_cycles'] == 0
    cycle[7]['rsp'] -= 8
    cycle[1]['add_id'] = 100
    assert report.intervening_cycles(cycle)['exact_contiguous_cycles'] == 0
    with tempfile.TemporaryDirectory(prefix='mif-accumulator-report-') as temp:
        path = Path(temp)/'trace.jsonl'
        path.write_text(cap.file.getvalue())
        assert len(report.report(path).splitlines()) < 20
        assert path.with_suffix('.events.csv').exists()
        legacy = [{'seq': 0, 'event': 'capture_start', 'game_base': 0x140000000}]
        for index, control in enumerate((10., 10.5)):
            before_blob, after_blob = bytearray(0xA6C), bytearray(0xA6C)
            for b in (before_blob, after_blob):
                struct.pack_into('<d', b, 0x318-0x300, control)
            struct.pack_into('<d', after_blob, 0x530-0x300, 0.5)
            seq = index*2+1
            common = {'receiver': obj, 'rsp': rsp, 'thread': 't', 'camera_id': index,
                      'output_target': 0x143564E20, 'branch': 'Mouse'}
            legacy += [dict(common, event='x_mouse_output', seq=seq, output=0.2,
                            receiver_300_d6c=before_blob.hex()),
                       dict(common, event='x_mouse_after', seq=seq+1, output_id=seq,
                            receiver_300_d6c=after_blob.hex())]
        path.write_text(''.join(json.dumps(r)+'\n' for r in legacy))
        prefix = Path(temp)/'legacy'
        report.legacy_report(path, prefix)
        decoded = json.loads(prefix.with_suffix('.json').read_text())
        assert decoded['paired_x_outputs'] == decoded['accumulator_changed'] == 2
        assert decoded['exact_checkpoint_matches'] == 1
        # Receiver identity corruption must not produce a healthy pair.
        legacy[-1]['receiver'] += 8
        path.write_text(''.join(json.dumps(r)+'\n' for r in legacy))
        try:
            report.legacy_report(path, prefix)
            raise AssertionError('Accepted mismatched legacy receiver')
        except ValueError:
            pass
    # All live probe/guard checks run before installing breakpoints. Validate
    # relocated addresses and reject one corrupted byte at every checked span.
    relocated, image_bytes = 0x180000000, {}
    for entry in module['SITES']['sites'].values():
        image_bytes.update({relocated+entry['rva']+i: b for i, b in enumerate(bytes.fromhex(entry['bytes']))})
    for rva, signature in module['SITES']['guards'].items():
        image_bytes.update({relocated+int(rva, 16)+i: b for i, b in enumerate(bytes.fromhex(signature))})
    glob['memory'] = lambda a, n: bytes(image_bytes[a+i] for i in range(n))
    validated = []
    glob['camera'].Capture.validate = lambda self: validated.append(self.game)
    module['validate'](relocated)
    assert validated == [relocated]
    checks = [r['rva'] for r in module['SITES']['sites'].values()]
    checks += [int(r, 16) for r in module['SITES']['guards']]
    for rva in checks:
        address = relocated+rva
        image_bytes[address] ^= 1
        try:
            module['validate'](relocated)
            raise AssertionError('Accepted corrupt live bytes')
        except ValueError:
            pass
        finally:
            image_bytes[address] ^= 1
    print('PASS accumulator decoder, receiver filtering, setter/consumer pairing, vector clears, unknown writers, report')
    print('PASS relocated live validation and rejection at every probe/guard')


def hardware():
    with tempfile.TemporaryDirectory(prefix='mif-accumulator-gdb-') as temp:
        work = Path(temp)
        source = work/'fixture.c'
        source.write_text('''
#include <pthread.h>
unsigned char receiver[0x600] __attribute__((aligned(16)));
__attribute__((noinline)) void marker(void) { __asm__ volatile("nop"); }
void *worker(void *unused) {
    volatile double *yaw = (volatile double *)(receiver + 0x530);
    *yaw = 0.75;
    *yaw = -0.25;
    return 0;
}
int main(void) {
    volatile double *yaw = (volatile double *)(receiver + 0x530);
    marker();
    *yaw = 1.25;
    *yaw = -0.5;
    __asm__ volatile("xorps %%xmm0, %%xmm0; movups %%xmm0, (%0)"
                     : : "r"(receiver + 0x528) : "xmm0", "memory");
    *yaw = 0.0; /* unchanged bits: not reported by a write watchpoint */
    pthread_t thread;
    pthread_create(&thread, 0, worker, 0);
    pthread_join(thread, 0);
    marker();
    return 0;
}
''')
        subprocess.run(['cc', '-g', '-O0', '-pthread', str(source), '-o', str(work/'fixture')], check=True)
        script = work/'check.gdb'
        observer = ROOT/'tools/camera_accumulator_capture.py'
        script.write_text(f'''set pagination off
set confirm off
set debuginfod enabled off
break marker
run
source {observer}
python
import io
cap = Capture.__new__(Capture)
cap.obj = int(gdb.parse_and_eval("&receiver[0]"))
cap.base = 0
cap.vtable = 0
cap.count = 0
cap.label = 'native-fixture'
cap.recording = cap.sampling = True
cap.ready = 0
cap.end = time.monotonic() + 30
cap.file = io.StringIO()
cap.last_value = 0.0
cap.last_bits = bytes(8)
cap.adds = {{}}
cap.watch = WriteProbe(cap)
cap.breakpoints = [cap.watch]
assert cap.watch.type == gdb.BP_HARDWARE_WATCHPOINT
cap.watch.enabled = False
cap.watch.enabled = True
end
continue
python
rows = [json.loads(s) for s in cap.file.getvalue().splitlines()]
assert [r['after'] for r in rows] == [1.25, -0.5, 0.0, 0.75, -0.25], rows
assert [r['before'] for r in rows] == [0.0, 1.25, -0.5, 0.0, 0.75], rows
assert len(set(r['thread'] for r in rows)) == 2, rows
assert all(r['event'] == 'write' and r['writer'] == 'unknown' for r in rows)
cap.finish('fixture_complete')
assert len(gdb.breakpoints()) == 1, gdb.breakpoints()
print('PASS real eight-byte hardware watchpoint, scalar/vector changes, unchanged-store omission, cleanup')
end
continue
''')
        completed = subprocess.run(['gdb', '-q', '-nx', '-batch', '-x', str(script), str(work/'fixture')],
                                   text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(completed.stdout)
        if completed.returncode or 'PASS real eight-byte hardware' not in completed.stdout:
            raise RuntimeError('GDB hardware-watchpoint fixture failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gdb', action='store_true')
    args = parser.parse_args()
    offline()
    if args.gdb:
        hardware()
