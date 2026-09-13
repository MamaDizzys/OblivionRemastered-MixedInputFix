"""GDB: one receiver's yaw accumulator and its immediate consumers.

No inferior calls or game-state edits. One hardware write watchpoint catches
changed writes through aliases too; same-value writes are not reported by GDB.
The imported camera module supplies candidate validation, not active probes.
"""
import importlib.util
import json
from pathlib import Path
import time
import gdb


def tool_directory():
    return Path(tool_directory.__code__.co_filename).resolve().parent


DIRECTORY = tool_directory()
spec = importlib.util.spec_from_file_location('mif_camera_validation', DIRECTORY / 'camera_capture.py')
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)
SITES = json.loads((DIRECTORY / 'camera_accumulator_sites.json').read_text())
reg, memory, unpack, u64 = camera.reg, camera.memory, camera.unpack, camera.u64
ACTIVE = None
FINDER = None
SELECTED = None
LAST_OUTPUT = None


def double_register(name):
    return float(gdb.parse_and_eval('$' + name + '.v2_double[0]'))


def vector(address):
    return list(unpack(address, 'ddd'))


def validate(base):
    if camera.ACTIVE:
        raise ValueError('Stop the camera observer first')
    validator = camera.Capture.__new__(camera.Capture)
    validator.game = base
    validator.validate()
    for site in SITES['sites'].values():
        expected = bytes.fromhex(site['bytes'])
        if memory(base + site['rva'], len(expected)) != expected:
            raise ValueError('Accumulator probe bytes differ at RVA 0x%x' % site['rva'])
    for rva, signature in SITES['guards'].items():
        expected = bytes.fromhex(signature)
        if memory(base + int(rva, 16), len(expected)) != expected:
            raise ValueError('Accumulator guard differs at RVA ' + rva)


def receiver_layout(base, obj):
    vt = u64(obj)
    for offset, rva in ((0xD18, 0x3564E20), (0x760, 0x30BACE0),
                        (0x768, 0x30D1C90), (0xC00, 0x359B340)):
        if u64(vt + offset) != base + rva:
            raise ValueError('Receiver virtual target differs at slot 0x%x' % offset)
    vector(obj + 0x528)
    vector(obj + 0x310)
    return vt


def require_idle_debugger():
    if any(bp.is_valid() and bp.enabled for bp in (gdb.breakpoints() or ())):
        raise ValueError('Use a fresh GDB session or stop/disable existing probes before this capture')


def caller_label(base, address):
    # Native call-site identity only; this is not a new provenance decoder.
    return {0x489DB0B: 'x_mouse_handler', 0x489D8CF: 'x_gamepad_handler'}.get(
        address - base, 'other_caller')


class Finder(gdb.Breakpoint):
    def __init__(self, base):
        super().__init__('*0x%x' % (base + SITES['sites']['add']['rva']), internal=True)
        self.base, self.silent = base, True

    def stop(self):
        global SELECTED
        try:
            obj = reg('rbx')
            vt = receiver_layout(self.base, obj)
            SELECTED = (gdb.selected_inferior().pid, self.base, obj, vt)
            gdb.write('Selected live X receiver 0x%x; stopped before accumulator add.\n'
                      'Arm mif-accumulator-trial LABEL, then continue.\n' % obj)
        except Exception as error:
            SELECTED = None
            gdb.write('Receiver validation failed: %s\n' % error)
        gdb.post_event(remove_finder)
        return True


def remove_finder():
    global FINDER
    if FINDER and FINDER.is_valid():
        FINDER.delete()
    FINDER = None


class Probe(gdb.Breakpoint):
    def __init__(self, capture, name, address):
        super().__init__('*0x%x' % address, internal=True)
        self.capture, self.name, self.silent = capture, name, True

    def stop(self):
        return self.capture.hit(self.name)


class WriteProbe(gdb.Breakpoint):
    def __init__(self, capture):
        super().__init__('*(unsigned long long*)0x%x' % (capture.obj + 0x530),
                         type=gdb.BP_WATCHPOINT, wp_class=gdb.WP_WRITE, internal=True)
        self.capture, self.silent = capture, True
        if self.type != gdb.BP_HARDWARE_WATCHPOINT:
            self.delete()
            raise ValueError('An eight-byte HARDWARE watchpoint is required; no software fallback')

    def stop(self):
        return self.capture.hit('write')


class Capture:
    def __init__(self, selected, output, label):
        self.pid, self.base, self.obj, self.vtable = selected
        if self.pid != gdb.selected_inferior().pid:
            raise ValueError('Inferior changed; run mif-accumulator-find again')
        validate(self.base)
        if receiver_layout(self.base, self.obj) != self.vtable:
            raise ValueError('Receiver changed; run mif-accumulator-find again')
        if not gdb.parameter('can-use-hw-watchpoints'):
            raise ValueError('Hardware watchpoints are disabled in this GDB session')
        self.breakpoints, self.adds, self.consumers, self.setters, self.signs = [], {}, {}, {}, {}
        self.count, self.label, self.recording = 0, label, True
        self.ready, self.end, self.sampling = None, None, False
        self.file = open(output, 'x', encoding='utf-8')
        try:
            self.write({'event': 'capture_start', 'receiver': self.obj, 'vtable': self.vtable,
                        'consumer_target': u64(self.vtable + 0xC00),
                        'additional_consumer_target': u64(self.vtable + 0xBE0),
                        'game_base': self.base, 'pid': self.pid, 'game_sha256': SITES['game_sha256'],
                        'candidate_sha256': camera.SITES['candidate_sha256'],
                        'validation': 'Exact live helper/probe/guard bytes, not a loaded-image hash',
                        'limit': 2000, 'preparation_seconds': 8, 'sample_seconds': 3,
                        'note': 'One hardware watchpoint; changed writes only. GDB perturbs timing.'})
            # Construct before continuing; fail closed if hardware is unavailable.
            self.watch = WriteProbe(self)
            self.breakpoints.append(self.watch)
            self.watch.enabled = False
            for name, site in SITES['sites'].items():
                bp = Probe(self, name, self.base + site['rva'])
                self.breakpoints.append(bp)
                bp.enabled = name == 'add'
        except Exception:
            self.finish('setup_error')
            raise

    def write(self, row):
        row.update(seq=self.count, label=self.label, host_time=time.monotonic())
        self.file.write(json.dumps(camera.clean(row), allow_nan=False) + '\n')
        self.count += 1

    def snapshot(self):
        return {'accumulator': vector(self.obj + 0x528),
                'yaw_bits': memory(self.obj + 0x530, 8).hex(),
                'control_rotation': vector(self.obj + 0x310)}

    def hit(self, name):
        if not self.recording:
            return False
        try:
            if name != 'write' and reg(SITES['sites'][name]['receiver_register']) != self.obj:
                return False
            now = time.monotonic()
            if self.ready is None:
                self.ready = now + 8
            if now < self.ready:
                return False
            if not self.sampling:
                if name != 'add':
                    return False
                if u64(self.obj) != self.vtable:
                    raise ValueError('Selected receiver vtable changed')
                self.sampling, self.end = True, now + 3
                self.last_bits = memory(self.obj + 0x530, 8)
                self.last_value = unpack(self.obj + 0x530, 'd')[0]
                self.write({'event': 'sample_start', 'receiver': self.obj, **self.snapshot()})
                for bp in self.breakpoints:
                    bp.enabled = True
            if u64(self.obj) != self.vtable:
                raise ValueError('Selected receiver vtable changed')
            thread = str(gdb.selected_thread().ptid)
            rsp, pc = reg('rsp'), reg('rip')
            row = {'event': name, 'thread': thread, 'rsp': rsp, 'pc': pc,
                   'receiver': self.obj, **self.snapshot()}
            key = (thread, rsp)
            if name == 'add':
                caller = u64(rsp + 0x38)
                row.update(contribution=double_register('xmm0'), caller=caller,
                           caller_kind=caller_label(self.base, caller))
                self.adds[key] = self.count
            elif name == 'write':
                after = memory(self.obj + 0x530, 8)
                row.update(before=self.last_value, before_bits=self.last_bits.hex(),
                           after=row['accumulator'][1], after_bits=after.hex(),
                           writer=SITES['changed_write_pcs'].get(hex(pc - self.base), 'unknown'))
                self.last_bits, self.last_value = after, row['after']
                if row['writer'] == 'native_add':
                    caller = u64(rsp + 0x38)
                    row.update(add_id=self.adds.pop(key, None), caller=caller,
                               caller_kind=caller_label(self.base, caller))
                elif row['writer'] == 'unknown':
                    # PC is AFTER the write. Do not invent an instruction start.
                    try:
                        row['backtrace'] = gdb.execute('bt 6', to_string=True)
                    except Exception as error:
                        row['backtrace_error'] = str(error)
                    row['registers'] = {r: reg(r) for r in ('rax', 'rbx', 'rcx', 'rdx',
                                                           'rsi', 'rdi', 'r8', 'r9', 'r10', 'r11')}
            elif name == 'consume':
                self.consumers[key] = self.count
                manager = u64(self.obj + 0x350)
                row.update(consumer_id=self.count, manager=manager,
                           manager_target=u64(u64(manager) + 0x868) if manager else None)
            elif name in ('manager_before', 'manager_after'):
                row.update(consumer_id=self.consumers.get(key),
                           view_rotation=vector(rsp + 0x30), local_delta=vector(rsp + 0x48))
                if name == 'manager_before':
                    row.update(manager=reg('rcx'), manager_target=u64(reg('rax') + 0x868))
            elif name == 'set_enter':
                caller = u64(rsp)
                row.update(set_id=self.count, caller=caller, requested_rotation=vector(reg('rdx')),
                           consumer_id=self.consumers.get((thread, rsp + 8))
                           if caller == self.base + 0x359B4E6 else None,
                           sign_id=self.signs.get((thread, rsp + 8))
                           if caller == self.base + 0x488FB7B else None)
                self.setters[key] = self.count
            elif name == 'set_return':
                row['set_id'] = self.setters.pop((thread, rsp + 0xB8), None)
            elif name in ('sign_test', 'sign_skip', 'sign_submit'):
                if name == 'sign_test':
                    self.signs[key] = self.count
                row.update(computed_yaw_delta=double_register('xmm3'),
                           sign_id=self.signs.get(key),
                           comparison_zero=double_register('xmm10'),
                           proposed_rotation=vector(rsp + 0x50),
                           state_928_958=memory(self.obj + 0x928, 0x30).hex())
            elif name == 'history_copy':
                row.update(previous_input_history=vector(self.obj + 0x9A0),
                           copy_pitch=double_register('xmm0'),
                           copy_yaw=float(gdb.parse_and_eval('$xmm0.v2_double[1]')),
                           copy_roll=double_register('xmm1'))
            self.write(row)
            if self.count >= 2000:
                return self.request_finish('event_limit')
            if now >= self.end:
                if name == 'write' and row.get('writer', '').endswith('_clear'):
                    return self.request_finish('timed_clear_boundary')
                if now >= self.end + 2:
                    return self.request_finish('timed_partial')
        except Exception as error:
            self.write({'event': 'capture_error', 'site': name, 'error': str(error)})
            return self.request_finish('read_or_layout_error')
        return False

    def request_finish(self, reason):
        self.recording = False
        gdb.post_event(lambda: self.finish(reason))
        return True

    def finish(self, reason='user_stop'):
        global ACTIVE
        self.recording = False
        for bp in self.breakpoints:
            if bp.is_valid():
                bp.delete()
        self.breakpoints.clear()
        if not self.file.closed:
            self.write({'event': 'capture_end', 'reason': reason,
                        'note': 'First/last consumer intervals may be partial; unchanged writes omitted.'})
            self.file.close()
        if ACTIVE is self:
            ACTIVE = None
        gdb.write('Accumulator capture closed (%s); its probes removed.\n' % reason)


class Find(gdb.Command):
    """mif-accumulator-find [GAME_BASE=$mif_base]: validate, then stop at next X add."""
    def __init__(self):
        super().__init__('mif-accumulator-find', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global FINDER, SELECTED
        if ACTIVE or FINDER:
            raise gdb.GdbError('Use mif-accumulator-stop first')
        SELECTED = None
        try:
            require_idle_debugger()
            base = int(gdb.parse_and_eval(arg.strip() or '$mif_base'))
            validate(base)
            FINDER = Finder(base)
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Continue and move X briefly; stop at the next native X accumulator add.\n')


class Trial(gdb.Command):
    """mif-accumulator-trial LABEL: 8s prep, 3s sample, 2000 events; one receiver."""
    def __init__(self):
        super().__init__('mif-accumulator-trial', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global ACTIVE, LAST_OUTPUT
        label = arg.strip()
        if not label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in label):
            raise gdb.GdbError('Usage: mif-accumulator-trial LABEL (letters/digits/_/-)')
        if ACTIVE or FINDER or not SELECTED:
            raise gdb.GdbError('Stop existing capture and complete mif-accumulator-find first')
        output = '/tmp/mif-accumulator-%s-%d.jsonl' % (label, time.time_ns())
        try:
            require_idle_debugger()
            ACTIVE = Capture(SELECTED, output, label)
            LAST_OUTPUT = output
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Continue: 8 seconds preparation, then 3 seconds sampling.\n'
                  'If still running after about 15 seconds: Ctrl+C, mif-accumulator-stop.\n' + output + '\n')


class Stop(gdb.Command):
    """mif-accumulator-stop: remove only this observer's probes and flush."""
    def __init__(self):
        super().__init__('mif-accumulator-stop', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        remove_finder()
        if ACTIVE:
            ACTIVE.finish()


class Report(gdb.Command):
    """mif-accumulator-report [FILE]: write event CSV and bounded factual summary."""
    def __init__(self):
        super().__init__('mif-accumulator-report', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            raise gdb.GdbError('Use mif-accumulator-stop first')
        args = gdb.string_to_argv(arg)
        if len(args) > 1 or (not args and not LAST_OUTPUT):
            raise gdb.GdbError('Usage: mif-accumulator-report [FILE]')
        spec = importlib.util.spec_from_file_location('mif_accumulator_report', DIRECTORY / 'analyze_camera_accumulator.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gdb.write(module.report(Path(args[0] if args else LAST_OUTPUT)) + '\n')


Find()
Trial()
Stop()
Report()
gdb.write('Accumulator commands loaded; no probes installed. Use mif-camera-base, then mif-accumulator-find.\n')
