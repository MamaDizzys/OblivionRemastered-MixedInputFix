"""Source in GDB; explicit mif-camera-start installs bounded, observing breakpoints.
No inferior calls, register edits, return thunks, or replacement DLL are used.
Specific to the production DLL SHA recorded in camera_capture_sites.json.
"""
import json
import math
import importlib.util
from pathlib import Path
import struct
import time
import gdb

def _tool_directory():
    # GDB source can omit __file__ or retain one from another script.
    return Path(_tool_directory.__code__.co_filename).resolve().parent


TOOL_DIRECTORY = _tool_directory()
SITES = json.loads((TOOL_DIRECTORY / 'camera_capture_sites.json').read_text())
ACTIVE = None
LAST_OUTPUT = None
KEYS = {'MouseX': 0x91132C0, 'MouseY': 0x91132D8,
        'Gamepad_RightX': 0x9113F20, 'Gamepad_RightY': 0x9113F38}
SOURCE = {0: 'Unknown', 1: 'Mouse', 2: 'Gamepad', 3: 'Digital', 4: 'LeftStick'}
AXIS = {0: 'Unknown', 1: 'X', 2: 'Y'}


def reg(name):
    return int(gdb.selected_frame().read_register(name)) & ((1 << 64) - 1)


def memory(address, size):
    if not address:
        raise ValueError('null memory address')
    return bytes(gdb.selected_inferior().read_memory(address, size))


def unpack(address, fmt):
    return struct.unpack('<' + fmt, memory(address, struct.calcsize('<' + fmt)))


def u64(address):
    return unpack(address, 'Q')[0]


def value(address):
    x, y, z, kind = unpack(address, 'dddB')
    return {'xyz': [x, y, z], 'type': kind}


def xmm_float(name):
    return float(gdb.parse_and_eval('$' + name + '.v4_float[0]'))


def clean(obj):
    if isinstance(obj, float) and not math.isfinite(obj):
        return repr(obj)
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    return obj


class Probe(gdb.Breakpoint):
    def __init__(self, capture, name, address):
        super().__init__('*0x%x' % address, internal=True)
        self.silent = True
        self.capture, self.name = capture, name

    def stop(self):
        return self.capture.hit(self.name)


class Capture:
    def __init__(self, game, output, limit, trial=False):
        self.game, self.limit = game, limit
        self.breakpoints, self.threads, self.targets = [], {}, set()
        self.count, self.label, self.recording = 0, 'unlabelled', True
        self.file = None
        self.timing = {'ready': None, 'end': None} if trial else None
        self.validate()  # All reads/shape checks before installing any breakpoint.
        self.file = open(output, 'x', encoding='utf-8')
        try:
            self.write({'event': 'capture_start', 'game_base': game, 'dll_base': self.dll,
                        'candidate_sha256': SITES['candidate_sha256'], 'limit': limit,
                        'validation': 'Exact helper/probe bytes; not a full loaded-DLL hash',
                        'trial': trial,
                        'note': 'GDB stops perturb timing; values are observations, not a cause verdict.'})
            for name, site in SITES['game_sites'].items():
                self.breakpoints.append(Probe(self, name, game + site['rva']))
            self.breakpoints.append(Probe(self, 'tls_ready', self.helper + 0x13))
            self.breakpoints.append(Probe(self, 'reset', self.shim + 0x4C))
            self.breakpoints.append(Probe(self, 'dispatch_begin', game + 0x392CD15))
            if trial:
                self.sample_probes(False)
        except Exception:
            self.finish('setup_error')
            raise

    def sample_probes(self, enabled):
        # Only two reset-related stops per evaluation during preparation.
        for bp in self.breakpoints:
            if bp.name not in ('tls_ready', 'reset'):
                bp.enabled = enabled

    def validate(self):
        call = self.game + 0x392B6A6
        if memory(call, 1) != b'\xe8':
            raise ValueError('Expected installed five-byte reset CALL')
        self.shim = call + 5 + unpack(call + 1, 'i')[0]
        if memory(self.shim, 8) != bytes.fromhex('9c4881ec60020000'):
            raise ValueError('Not the validated reset/generation shim')
        if memory(self.shim + 0x40, 2) != b'\x48\xb8':
            raise ValueError('Unexpected reset helper load')
        self.helper = u64(self.shim + 0x42)
        self.dll = self.helper - SITES['helper_rva']
        if memory(self.dll, 2) != b'MZ':
            raise ValueError('Cannot identify production DLL base')
        for address, expected in [(self.helper, SITES['helper_bytes']),
                                  (self.dll + SITES['input_type_rva'], SITES['input_type_bytes'])]:
            data = bytes.fromhex(expected)
            if memory(address, len(data)) != data:
                raise ValueError('DLL helper/layout differs from candidate ' + SITES['candidate_sha256'])
        if memory(self.shim + 0x75, 14) != bytes.fromhex('4881c4600200009dff2500000000'):
            raise ValueError('Unexpected reset restore/tail encoding')
        if u64(self.shim + 0x83) != self.game + 0x3939FA0:
            raise ValueError('Unexpected original reset target')
        if memory(self.shim + 0x4A, 8) != bytes.fromhex('ffd0480fae4c2460'):
            raise ValueError('Unexpected reset return probe encoding')
        for rva, offset in ((0x489D2F9, 0x400), (0x488A0E9, 0x600)):
            call = self.game + rva
            if memory(call, 1) != b'\xe8' or call + 5 + unpack(call + 1, 'i')[0] != self.shim - 0xB00 + offset:
                raise ValueError('Camera getter redirect differs from production')
        for rva in (0x488AC43, 0x488AD39, 0x488AE33, 0x488AF29):
            if memory(self.game + rva, 2) != b'\x75\x0f':
                raise ValueError('Expected live-verified original movement branches')
        site = self.game + 0x392CD15
        if memory(site, 2) != b'\xff\x15':
            raise ValueError('Expected six-byte dispatch CALL')
        slot = site + 6 + unpack(site + 2, 'i')[0]
        if slot != self.shim - 0xB00 + 0xA10 or u64(slot) != self.shim - 0xB00 + 0x200:
            raise ValueError('Dispatch bridge is not from the reset page')
        for name, item in SITES['game_sites'].items():
            expected = bytes.fromhex(item['bytes'])
            if memory(self.game + item['rva'], len(expected)) != expected:
                raise ValueError('Game bytes differ at ' + name + '; remove conflicting breakpoints first')

    def write(self, row):
        row.update(seq=self.count, label=self.label, host_time=time.monotonic())
        self.file.write(json.dumps(clean(row), allow_nan=False) + '\n')
        self.count += 1

    def state(self):
        key = str(gdb.selected_thread().ptid)
        return key, self.threads.setdefault(key, {'tls': None, 'dispatches': [], 'cameras': [], 'actions': set()})

    def provenance(self, state, instance=None):
        if state['tls'] is None:
            return {'available': False}
        p = state['tls'] + SITES['tls_provenance_offset']
        owner, frame, generation = unpack(p, 'QQQ')
        count = u64(p + 0xC18)
        valid, exhausted = unpack(p + 0xC20, 'BB')
        if count > 128:
            raise ValueError('provenance count exceeds verified layout')
        result = {'available': True, 'owner': owner, 'frame': frame, 'generation': generation,
                  'valid': bool(valid), 'exhausted': bool(exhausted)}
        scope = u64(state['tls'] + SITES['tls_dispatch_offset'])
        if scope:
            so, sf, sg, action, scope_instance, source, axis = unpack(scope, 'QQQQQBB')
            result['scope'] = {'pointer': scope, 'owner': so, 'frame': sf, 'generation': sg,
                               'action': action, 'instance': scope_instance, 'source': SOURCE.get(source, str(source)),
                               'axis': AXIS.get(axis, str(axis)),
                               'generation_matches': bool(valid and sg and (so, sf, sg) == (owner, frame, generation))}
            if instance is None:
                instance = scope_instance
        if instance:
            action = u64(instance)
            result['record'] = {'source': 'Unknown', 'axis': 'Unknown', 'found': False}
            for i in range(count):
                entry_action, entry_instance, source, axis = unpack(p + 24 + i * 24, 'QQBB')
                if entry_action == action:
                    result['record'] = {'source': SOURCE.get(source, str(source)), 'axis': AXIS.get(axis, str(axis)),
                                        'found': True, 'instance_matches': instance == entry_instance,
                                        'instance': entry_instance}
                    break
        return result

    def key(self, pointer):
        identity = u64(pointer)
        ids = {name: u64(self.game + rva) for name, rva in KEYS.items()}
        if not all(ids.values()) or len(set(ids.values())) != 4:
            return 'Unknown', identity
        return next((name for name, v in ids.items() if v == identity), 'Unknown'), identity

    def camera_state(self, obj):
        gy, gx, x, y = unpack(obj + 0xD5C, 'ffff')
        return {'gain_y': gy, 'gain_x': gx, 'latest_x': x, 'latest_y': y}

    def instance(self, instance):
        action = u64(instance)
        return {'instance': instance, 'action': action, 'policy': unpack(action + 0x51, 'B')[0],
                'value': value(instance + 0x38)}

    def hit(self, name):
        if not self.recording:
            return False
        try:
            thread, state = self.state()
            if name == 'tls_ready':
                state['tls'] = reg('r9')  # Verified helper instruction: TLS block already loaded.
                return False
            if self.timing:
                now = time.monotonic()
                if self.timing['ready'] is None:
                    self.timing['ready'] = now + 8.0
                if now < self.timing['ready']:
                    return False
                if self.timing['end'] is None:
                    if name != 'reset':
                        return False
                    self.timing['end'] = now + 3.0
                    self.sample_probes(True)
                elif now >= self.timing['end']:
                    if name == 'reset':
                        # Retain the boundary that closes the previous window.
                        self.write({'event': 'reset', 'thread': thread, 'rsp': reg('rsp'),
                                    'provenance': self.provenance(state), 'closing_boundary': True})
                        self.request_finish('timed_complete')
                        return True
                    if now >= self.timing['end'] + 2.0:
                        self.request_finish('timed_partial')
                        return True
            row = {'event': name, 'thread': thread, 'rsp': reg('rsp')}
            if name == 'reset':
                row['delta'] = xmm_float('xmm14')
                row['provenance'] = self.provenance(state)
                # Never keep stale camera/dispatch associations after unwind.
                # Nested frames are lower; live parent calls remain on the list.
                state['dispatches'] = [d for d in state['dispatches'] if d['rsp'] > row['rsp']]
                state['cameras'] = [c for c in state['cameras'] if c['rsp'] > row['rsp']]
            elif name.startswith('mapping') or name.startswith('merge'):
                frame, instance = reg('rbp'), reg('rdi')
                key, identity = self.key(u64(frame + 0x1F))
                action = u64(instance)
                # Keep even early unknown mappings; a later camera binding may
                # identify their action, or their winner may force fallback.
                row.update(self.instance(instance))
                row.update(key=key, key_identity=identity, mapping_frame=frame,
                           evaluation_frame=u64(frame + 0x37), owner=reg('r14'),
                           mapping_caller=u64(frame + 0x3F), key_pointer=u64(frame + 0x1F))
                row['provenance'] = self.provenance(state, instance)
                if name == 'mapping_input':
                    row['mapping_input'] = value(u64(frame + 0x67))
                else:
                    component = reg('rcx')
                    if component >= 3:
                        raise ValueError('Unexpected merge component')
                    row.update(component=component, candidate=unpack(frame - 0x49 + component * 8, 'd')[0],
                               accumulated=unpack(frame - 0x69 + component * 8, 'd')[0])
            elif name.startswith('action_'):
                row.update(self.instance(reg('rdi') + 8))
                row['provenance'] = self.provenance(state, row['instance'])
                modifiers, count = unpack(row['instance'] + 0x28, 'Qi')
                if count < 0 or count > 1024:
                    raise ValueError('Unexpected action modifier count')
                row['modifiers'] = {'count': count, 'sample': [u64(modifiers + 8*i) for i in range(min(count, 16))]}
                # Keep every action so a camera binding on a distinct action is
                # distinguishable from one combined logical action later.
            elif name == 'dispatch_begin':
                row.update(self.instance(reg('rdx')))
                row.update(binding=reg('rcx'), owner=reg('r13'), frame=reg('rbp'), dispatch_id=self.count)
                row['provenance'] = self.provenance(state, row['instance'])
                row['target'] = u64(u64(row['binding']) + 8)
                state['dispatches'] = [d for d in state['dispatches'] if d['rsp'] > row['rsp']]
                state['dispatches'].append(dict(row))
            elif name == 'dispatch_end':
                matching = [d for d in state['dispatches'] if d['rsp'] == row['rsp'] and d['frame'] == reg('rbp')]
                if matching:
                    row['dispatch_id'] = matching[-1]['dispatch_id']
                    state['dispatches'].remove(matching[-1])
                row['provenance'] = self.provenance(state)
            else:
                axis = name[0].upper()
                row.update(axis=axis, provenance=self.provenance(state))
                active = [d for d in state['dispatches'] if d['rsp'] > row['rsp']]
                row['dispatch_id'] = active[-1]['dispatch_id'] if active else None
                if name.endswith('_return'):
                    cam = next((c for c in reversed(state['cameras'])
                                if c['axis'] == axis and c['rsp'] == row['rsp']), None)
                    if cam is None:
                        return False  # Initial partial call.
                    row.update(camera=cam['camera'], camera_id=cam['camera_id'],
                               state=self.camera_state(cam['camera']))
                    state['cameras'].remove(cam)
                elif name.endswith('_entry') or name.endswith('_clear'):
                    obj = reg('rcx')
                    row['camera'] = obj
                    row['state'] = self.camera_state(obj)
                    if name.endswith('_entry'):
                        row['input'] = value(reg('rdx'))
                        state['cameras'] = [c for c in state['cameras'] if c['rsp'] > row['rsp']]
                        state['cameras'].append({'axis': axis, 'rsp': row['rsp'], 'camera': obj, 'camera_id': self.count})
                        row['camera_id'] = self.count
                else:
                    obj = reg('rsi')
                    row.update(camera=obj, state=self.camera_state(obj))
                    cam = [c for c in state['cameras'] if c['axis'] == axis and c['camera'] == obj and c['rsp'] > row['rsp']]
                    cam = cam[-1] if cam else None
                    row['camera_id'] = cam['camera_id'] if cam else None
                    if name.endswith('_getter_before'):
                        # Probe is the MOV RCX,RAX immediately before the CALL.
                        common = reg('rax')
                        row.update(common_input=common, common_type=unpack(common + 0x91, 'B')[0])
                        if cam is not None:
                            cam['common_input'] = common
                    if name.endswith('_branch'):
                        row['getter_result'] = reg('rax') & 255
                        common = cam.get('common_input') if cam else None
                        row.update(common_input=common,
                                   common_type=unpack(common + 0x91, 'B')[0] if common else None)
                    if name.endswith('_output'):
                        row['output'] = xmm_float('xmm1')
                        row['branch'] = 'Gamepad' if '_gamepad_' in name else 'Mouse'
                        receiver = reg('rcx')
                        row['receiver'] = receiver
                        vtable = u64(receiver)
                        target = u64(vtable + (0xD18 if axis == 'X' else 0xD10))
                        row['output_target'] = target
                        if target not in self.targets:
                            row['target_code'] = memory(target, 128).hex()
                            self.targets.add(target)
                        # Raw receiver snapshot permits locating the downstream
                        # accumulator from the dynamically resolved target code.
                        row['receiver_300_d6c'] = memory(receiver + 0x300, 0xA6C).hex()
                        if cam is not None:
                            cam['pending_output'] = (self.count, row['branch'], receiver, row['rsp'])
                    if name.endswith('_after'):
                        pending = cam.get('pending_output') if cam else None
                        branch = 'Gamepad' if '_gamepad_' in name else 'Mouse'
                        # Mouse return is also the common gamepad epilogue.
                        if not pending or pending[1] != branch or pending[3] != row['rsp']:
                            return False
                        row.update(output_id=pending[0], receiver=pending[2])
                        row['receiver_300_d6c'] = memory(pending[2] + 0x300, 0xA6C).hex()
                        del cam['pending_output']
            self.write(row)
        except Exception as error:
            self.write({'event': 'capture_error', 'site': name, 'error': str(error)})
            self.request_finish('read_or_layout_error')
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
            self.write({'event': 'capture_end', 'reason': reason, 'events_before_end': self.count})
            self.file.close()
        if ACTIVE is self:
            ACTIVE = None
        gdb.write('MixedInputFix capture closed (%s); its breakpoints removed.\n' % reason)


class Start(gdb.Command):
    """mif-camera-start GAME_BASE OUTPUT.jsonl [MAX_EVENTS=6000]
Start observing the exact validated production build. Does not resume execution.
At limit/error capture stops and removes its own breakpoints. Other breakpoints
must not overlap these sites. Capture initial/final generation windows may be partial.
"""
    def __init__(self):
        super().__init__('mif-camera-start', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global ACTIVE, LAST_OUTPUT
        if ACTIVE:
            raise gdb.GdbError('Capture already active; use mif-camera-stop first')
        args = gdb.string_to_argv(arg)
        if len(args) not in (2, 3):
            raise gdb.GdbError('Usage: mif-camera-start GAME_BASE OUTPUT.jsonl [MAX_EVENTS]')
        limit = int(args[2], 0) if len(args) == 3 else 6000
        if not 100 <= limit <= 20000:
            raise gdb.GdbError('MAX_EVENTS must be 100..20000')
        try:
            ACTIVE = Capture(int(args[0], 0), args[1], limit)
            LAST_OUTPUT = args[1]
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Capture armed; use mif-camera-mark LABEL, then continue. No game values changed.\n')


class Mark(gdb.Command):
    """mif-camera-mark LABEL: label the next capture segment while stopped."""
    def __init__(self):
        super().__init__('mif-camera-mark', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if not ACTIVE:
            raise gdb.GdbError('No active capture')
        ACTIVE.label = arg.strip()[:120] or 'unlabelled'
        ACTIVE.write({'event': 'mark'})


class Stop(gdb.Command):
    """mif-camera-stop: flush capture and remove only this script's breakpoints."""
    def __init__(self):
        super().__init__('mif-camera-stop', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            ACTIVE.finish()


class Base(gdb.Command):
    """mif-camera-base: validate the installed candidate and set $mif_base."""
    def __init__(self):
        super().__init__('mif-camera-base', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            raise gdb.GdbError('Stop capture before validating bytes')
        matches, failures = [], []
        try:
            for line in Path('/proc/%d/maps' % gdb.selected_inferior().pid).read_text().splitlines():
                parts = line.split(maxsplit=5)
                if len(parts) != 6 or not parts[5].endswith('/OblivionRemastered-Win64-Shipping.exe') or int(parts[2], 16):
                    continue
                cap = Capture.__new__(Capture)
                cap.game = int(parts[0].split('-')[0], 16)
                try:
                    cap.validate()
                    matches.append(cap.game)
                except Exception as error:
                    failures.append(str(error))
        except Exception as error:
            raise gdb.GdbError(str(error))
        if len(set(matches)) != 1:
            raise gdb.GdbError('Cannot validate one shipping base: %s; report info proc mappings. Do not guess.' % failures)
        base = matches[0]
        gdb.set_convenience_variable('mif_base', gdb.Value(base))
        gdb.write('Validated camera candidate helper/probe bytes; $mif_base = 0x%x\n' % base)


class Trial(gdb.Command):
    """mif-camera-trial LABEL [GAME_BASE=$mif_base]
New /tmp JSONL; 8 seconds preparation, 3 seconds contiguous sampling,
6000 row cap. Stop at next reset or after 2 extra seconds on a later probe.
"""
    def __init__(self):
        super().__init__('mif-camera-trial', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global ACTIVE, LAST_OUTPUT
        args = gdb.string_to_argv(arg)
        if len(args) not in (1, 2) or not args[0] or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args[0]):
            raise gdb.GdbError('Usage: mif-camera-trial LABEL [GAME_BASE]; label uses letters/digits/_/-')
        if ACTIVE:
            raise gdb.GdbError('Interrupt and mif-camera-stop before the next trial')
        output = '/tmp/mif-camera-%s-%d.jsonl' % (args[0], time.time_ns())
        try:
            base = int(gdb.parse_and_eval(args[1] if len(args) == 2 else '$mif_base'))
            ACTIVE = Capture(base, output, 6000, trial=True)
            ACTIVE.label = args[0]
            LAST_OUTPUT = output
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Continue and focus game: 8 seconds preparation, then 3 seconds contiguous capture.\n')
        gdb.write('6000 row cap; Ctrl+C then mif-camera-stop if not stopped after about 15 seconds.\n' + output + '\n')


class Report(gdb.Command):
    """mif-camera-report [FILE]: write full JSON/CSV summaries, print at most 150 lines."""
    def __init__(self):
        super().__init__('mif-camera-report', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            raise gdb.GdbError('Interrupt and mif-camera-stop before reporting')
        args = gdb.string_to_argv(arg)
        if len(args) > 1 or (not args and not LAST_OUTPUT):
            raise gdb.GdbError('Usage: mif-camera-report [FILE]')
        spec = importlib.util.spec_from_file_location('mif_camera_summary', TOOL_DIRECTORY / 'analyze_camera_capture.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gdb.write(module.report(Path(args[0] if args else LAST_OUTPUT)) + '\n')


Start()
Mark()
Stop()
Base()
Trial()
Report()
gdb.write('MixedInputFix camera capture commands loaded; no breakpoints installed yet.\n')
