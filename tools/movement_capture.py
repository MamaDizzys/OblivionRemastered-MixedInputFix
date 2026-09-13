"""GDB observer for the NOP baseline or movement candidate; source, then start.
Records values only: no inferior calls, register edits, or replacement patches.
Software breakpoints perturb timing. Capture generation is an observer counter,
not a read of production TLS. Start/stop windows can contain partial evaluations.
"""
import json
import math
import importlib.util
from pathlib import Path
import struct
import time
import gdb

def _tool_directory():
    # GDB source may omit __file__ (or retain one from an unrelated script).
    # The compiled function retains this script's source filename independently.
    for filename in (_tool_directory.__code__.co_filename, globals().get('__file__')):
        if filename and not filename.startswith('<'):
            directory = Path(filename).resolve().parent
            if all((directory / name).is_file() for name in
                   ('movement_capture_sites.json', 'movement_summary.py')):
                return directory
    raise gdb.GdbError('Cannot locate movement observer companions beside its source file')


TOOL_DIRECTORY = _tool_directory()
MANIFEST = json.loads((TOOL_DIRECTORY / 'movement_capture_sites.json').read_text())
ACTIVE = None
LAST_OUTPUT = None
KEYS = {'Gamepad_LeftX': 0x9113ED8, 'Gamepad_LeftY': 0x9113EF0,
        'MouseX': 0x91132C0, 'MouseY': 0x91132D8,
        'Gamepad_RightX': 0x9113F20, 'Gamepad_RightY': 0x9113F38}
DIRECTIONS = ('backward', 'forward', 'left', 'right')


def site_matches(base, name, site):
    expected = bytes.fromhex(site['bytes'])
    actual = memory(base + site['rva'], len(expected))
    if name.endswith('_branch'):
        restored = expected[:2] + b'\x75\x0f' + expected[4:]
        return actual in (expected, restored)
    return actual == expected


def reg(name):
    return int(gdb.selected_frame().read_register(name)) & ((1 << 64) - 1)


def memory(address, size):
    if not address:
        raise ValueError('Null address')
    return bytes(gdb.selected_inferior().read_memory(address, size))


def unpack(address, fmt):
    return struct.unpack('<' + fmt, memory(address, struct.calcsize('<' + fmt)))


def u64(address):
    return unpack(address, 'Q')[0]


def value(address):
    x, y, z, kind = unpack(address, 'dddB')
    return {'xyz': [x, y, z], 'type': kind}


def xmm(number, kind='float'):
    return float(gdb.parse_and_eval('$xmm%d.v%d_%s[0]' %
                                   (number, 4 if kind == 'float' else 2, kind)))


def clean(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        return repr(obj)
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


def caches(obj):
    f, b, l, r = unpack(obj + 0xD4C, 'ffff')
    return {'forward': f, 'backward': b, 'left': l, 'right': r}


def instance_info(instance):
    action = u64(instance)
    return {'instance': instance, 'action': action,
            'policy': unpack(action + 0x51, 'B')[0], 'value': value(instance + 0x38)}


def key_metadata(key, identity):
    try:
        details = u64(key + 8)
        return {'details': details, 'identity_matches': u64(details) == identity,
                'type': unpack(details + 0x42, 'B')[0]} if details else {'details': 0}
    except Exception as error:
        return {'error': str(error)}  # Unknown metadata is a production fallback case.


class Probe(gdb.Breakpoint):
    def __init__(self, capture, name, address):
        super().__init__('*0x%x' % address, internal=True)
        self.silent = True
        self.capture, self.name = capture, name

    def stop(self):
        return self.capture.hit(self.name)


class Capture:
    def __init__(self, base, output, limit):
        self.base, self.limit = base, limit
        self.count, self.label, self.recording = 0, 'unlabelled', True
        self.threads, self.breakpoints, self.file = {}, [], None
        self.timing = None
        for name, site in MANIFEST['sites'].items():
            if not site_matches(base, name, site):
                raise ValueError('Unexpected bytes at ' + name)
        self.file = open(output, 'x', encoding='utf-8')
        try:
            self.write({'event': 'capture_start', 'game_base': base,
                        'baseline_candidate': MANIFEST['candidate_sha256'],
                        'movement_branches': {d: memory(base + MANIFEST['sites'][d + '_branch']['rva'] + 2, 2).hex()
                                              for d in DIRECTIONS},
                        'validation': 'probe bytes only; not a full loaded-DLL hash', 'limit': limit})
            for name, site in MANIFEST['sites'].items():
                self.breakpoints.append(Probe(self, name, base + site['rva']))
        except Exception:
            self.finish('setup_error')
            raise

    def write(self, row):
        row.update(seq=self.count, label=self.label, host_time=time.monotonic())
        self.file.write(json.dumps(clean(row), allow_nan=False) + '\n')
        self.count += 1

    def hit(self, name):
        if not self.recording:
            return False
        try:
            thread = str(gdb.selected_thread().ptid)
            state = self.threads.setdefault(thread, {'generation': 0, 'owner': None,
                                                     'frame': None, 'dispatches': []})
            rsp = reg('rsp')
            timing = getattr(self, 'timing', None)
            if timing:
                now = time.monotonic()
                if getattr(self, 'arm_on_hit', False):
                    timing['ready'] = now + 8.0
                    self.arm_on_hit = False
                if now < timing['ready']:
                    return False
                if now >= timing['ready'] + 5.0:
                    self.request_finish('timed_partial')
                    return True
                if name == 'reset':
                    if state.get('sample'):
                        self.write({'event': 'window_end', 'thread': thread,
                                    'observed_generation': state['generation'],
                                    'owner': state['owner'], 'evaluation_frame': state['frame'],
                                    'same_identity': (state['owner'], state['frame']) == (reg('r13'), reg('rbp'))})
                    state['sample'] = False
                    if timing['end'] is None:
                        timing['end'] = now + 3.0
                        gdb.write('Movement sampling started (3 seconds).\n')
                    if now >= timing['end']:
                        self.request_finish('timed_complete')
                        return True
                    if now >= state.get('next_sample', 0):
                        state['sample'] = True
                        state['next_sample'] = now + 1.0
                elif now >= (timing['end'] or now) + 2.0:
                    self.request_finish('timed_partial')
                    return True
            if name == 'reset':
                state.update(generation=state['generation'] + 1, owner=reg('r13'), frame=reg('rbp'), common_inputs={})
                state['dispatches'] = [d for d in state['dispatches'] if d['rsp'] > rsp]
            if timing and not state.get('sample'):
                return False
            row = {'event': name, 'thread': thread, 'rsp': rsp,
                   'observed_generation': state['generation'], 'owner': state['owner'],
                   'evaluation_frame': state['frame']}
            active = [d for d in state['dispatches'] if d['rsp'] > rsp]
            row['dispatch_id'] = active[-1]['id'] if active else None
            if name == 'reset':
                row['delta'] = xmm(2)  # Probe precedes MOVAPS XMM14,XMM2.
            elif name in ('mapping_input', 'merge_before', 'merge_after'):
                frame, instance = reg('rbp'), reg('rdi')
                key_pointer = u64(frame + 0x1F)
                identity = u64(key_pointer)
                keys = {k: u64(self.base + v) for k, v in KEYS.items()}
                known = bool(identity and all(keys.values()) and len(set(keys.values())) == len(keys))
                row.update(instance_info(instance))
                row.update(mapping_frame=frame, mapping_owner=reg('r14'),
                           caller=u64(frame + 0x3F), saved_evaluation_frame=u64(frame + 0x37),
                           key_pointer=key_pointer, key_identity=identity,
                           key=next((k for k, v in keys.items() if known and v == identity), 'Other'))
                if name == 'mapping_input':
                    row['mapping_input'] = value(u64(frame + 0x67))
                    row['key_metadata'] = key_metadata(key_pointer, identity)
                else:
                    component = reg('rcx')
                    if component >= 3:
                        raise ValueError('Unexpected merge component')
                    row.update(component=component,
                               candidate=unpack(frame - 0x49 + component * 8, 'd')[0],
                               accumulated=unpack(frame - 0x69 + component * 8, 'd')[0])
            elif name in ('action_before', 'action_after'):
                row.update(instance_info(reg('rdi') + 8))
            elif name == 'dispatch_begin':
                row.update(instance_info(reg('rdx')))
                row.update(binding=reg('rcx'), dispatch_owner=reg('r13'), dispatch_frame=reg('rbp'),
                           dispatch_id=self.count, target=u64(u64(reg('rcx')) + 8))
                state['dispatches'] = [d for d in state['dispatches'] if d['rsp'] > rsp]
                state['dispatches'].append({'id': self.count, 'rsp': rsp, 'frame': reg('rbp')})
            elif name == 'dispatch_end':
                matches = [d for d in state['dispatches'] if d['rsp'] == rsp and d['frame'] == reg('rbp')]
                if matches:
                    row['dispatch_id'] = matches[-1]['id']
                    state['dispatches'].remove(matches[-1])
            elif name.startswith('consume_'):
                obj = reg('rdi')
                row.update(object=obj, caches=caches(obj))
                if name == 'consume_sum':
                    row.update(forward_sum=xmm(2, 'double'), right_sum=xmm(3, 'double'))
                if name == 'consume_final':
                    row.update(scaled_forward=xmm(0, 'double'), scaled_right=xmm(3, 'double'))
            else:
                direction, phase = name.split('_')
                if direction not in DIRECTIONS:
                    raise ValueError('Unexpected direction')
                obj = reg('rcx') if phase in ('entry', 'clear') else reg('rbx')
                row.update(object=obj, caches=caches(obj), direction=direction)
                if phase == 'entry':
                    row.update(input=value(reg('rdx')), return_address=u64(rsp))
                elif phase == 'getter':
                    # Capture RCX before the redirected CALL: helper calls are
                    # permitted to clobber RCX under the Windows ABI.
                    state.setdefault('common_inputs', {})[(rsp, direction)] = reg('rcx')
                elif phase == 'branch':
                    common = state.get('common_inputs', {}).pop((rsp, direction), None)
                    row.update(raw_float=xmm(6), getter_result=reg('rax') & 255,
                               common_input=common,
                               global_input_type=unpack(common + 0x91, 'B')[0] if common else None)
                elif phase == 'clear':
                    row['return_address'] = u64(rsp)
            self.write(row)
        except Exception as error:
            self.write({'event': 'capture_error', 'site': name, 'error': str(error)})
            self.request_finish('read_error')
            return True
        if self.count >= self.limit:
            self.request_finish('event_limit')
            return True
        return False

    def request_finish(self, reason):
        self.recording = False
        gdb.post_event(lambda: self.finish(reason))

    def finish(self, reason='user_stop'):
        global ACTIVE
        self.recording = False
        for bp in self.breakpoints:
            if bp.is_valid():
                bp.delete()
        self.breakpoints.clear()
        if self.file and not self.file.closed:
            self.write({'event': 'capture_end', 'reason': reason})
            self.file.close()
        if ACTIVE is self:
            ACTIVE = None
        gdb.write('Movement capture closed (%s); its breakpoints removed.\n' % reason)


class Start(gdb.Command):
    """mif-move-start GAME_BASE OUTPUT.jsonl [MAX_EVENTS=12000]; does not resume."""
    def __init__(self):
        super().__init__('mif-move-start', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global ACTIVE, LAST_OUTPUT
        if ACTIVE:
            raise gdb.GdbError('Capture already active')
        args = gdb.string_to_argv(arg)
        if len(args) not in (2, 3):
            raise gdb.GdbError('Usage: mif-move-start GAME_BASE OUTPUT.jsonl [MAX_EVENTS]')
        limit = int(args[2], 0) if len(args) == 3 else 12000
        if not 100 <= limit <= 30000:
            raise gdb.GdbError('MAX_EVENTS must be 100..30000')
        try:
            ACTIVE = Capture(int(gdb.parse_and_eval(args[0])), args[1], limit)
            LAST_OUTPUT = args[1]
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Movement capture armed; mark a trial and continue.\n')


class Mark(gdb.Command):
    """mif-move-mark LABEL; run while stopped before the labelled trial."""
    def __init__(self):
        super().__init__('mif-move-mark', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not ACTIVE:
            raise gdb.GdbError('No active capture')
        ACTIVE.label = arg.strip()[:120] or 'unlabelled'
        ACTIVE.write({'event': 'mark'})


class Stop(gdb.Command):
    """mif-move-stop; flush and remove only this observer's breakpoints."""
    def __init__(self):
        super().__init__('mif-move-stop', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            ACTIVE.finish()


class Trial(gdb.Command):
    """mif-move-trial LABEL [GAME_BASE=$mif_base]
Close any old capture; create a new unique /tmp/mif-move-LABEL-*.jsonl.
Then continue promptly and focus the game: 8 seconds preparation, 3 seconds
sampling (roughly one evaluation window per second), 900 recorded-event cap.
Stops automatically on a later probe; no inferior calls or value edits.
"""
    def __init__(self):
        super().__init__('mif-move-trial', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global ACTIVE, LAST_OUTPUT
        args = gdb.string_to_argv(arg)
        if len(args) not in (1, 2) or not args[0] or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args[0]):
            raise gdb.GdbError('Usage: mif-move-trial LABEL [GAME_BASE]; label uses letters/digits/_/-')
        if ACTIVE:
            ACTIVE.finish('replaced_by_trial')
        path = '/tmp/mif-move-%s-%d.jsonl' % (args[0], time.time_ns())
        try:
            base = int(gdb.parse_and_eval(args[1] if len(args) == 2 else '$mif_base'))
            ACTIVE = Capture(base, path, 900)
            ACTIVE.label = args[0]
            # Delay starts with the first running probe, not while entering commands.
            ACTIVE.timing = {'ready': float('inf'), 'end': None}
            ACTIVE.arm_on_hit = True
            LAST_OUTPUT = path
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Trial ready: continue, focus game, prepare input during first 8 seconds; sample for next 3.\n')
        gdb.write('At most 900 recorded events; no per-event console output. File: ' + path + '\n')


class Report(gdb.Command):
    """mif-move-report [FILE]; summarize the last closed capture, at most 150 lines."""
    def __init__(self):
        super().__init__('mif-move-report', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            raise gdb.GdbError('Capture still active; interrupt, then mif-move-stop first')
        args = gdb.string_to_argv(arg)
        if len(args) > 1 or (not args and not LAST_OUTPUT):
            raise gdb.GdbError('Usage: mif-move-report [FILE]')
        path = args[0] if args else LAST_OUTPUT
        spec = importlib.util.spec_from_file_location('mif_move_summary', TOOL_DIRECTORY / 'movement_summary.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gdb.write(module.report(Path(path)) + '\n')


class Base(gdb.Command):
    """mif-move-base: find and validate the local Linux inferior's shipping PE base.
Sets $mif_base; does not set breakpoints or call the inferior.
"""
    def __init__(self):
        super().__init__('mif-move-base', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            raise gdb.GdbError('Stop the capture before checking its probe bytes')
        pid = gdb.selected_inferior().pid
        matches = set()
        try:
            for line in Path('/proc/%d/maps' % pid).read_text().splitlines():
                parts = line.split(maxsplit=5)
                if len(parts) != 6 or not parts[5].endswith('/OblivionRemastered-Win64-Shipping.exe') or int(parts[2], 16):
                    continue
                base = int(parts[0].split('-')[0], 16)
                try:
                    if memory(base, 2) != b'MZ':
                        continue
                    if all(site_matches(base, name, site) for name, site in MANIFEST['sites'].items()):
                        matches.add(base)
                except Exception:
                    continue
        except Exception as error:
            raise gdb.GdbError('Cannot read local inferior mappings: ' + str(error))
        if len(matches) != 1:
            raise gdb.GdbError('Cannot uniquely validate shipping base; paste this error and info proc mappings. Do not guess.')
        base = matches.pop()
        gdb.set_convenience_variable('mif_base', gdb.Value(base))
        gdb.write('Validated movement probe bytes; $mif_base = 0x%x\n' % base)


Start()
Mark()
Stop()
Trial()
Report()
Base()
gdb.write('Movement capture commands loaded; no breakpoints installed.\n')
