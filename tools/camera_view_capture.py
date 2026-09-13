"""GDB: one hardware execution checkpoint after the camera view getter's copies.

No inferior calls or game-state edits. Rows are buffered until stop. This is a
returned manager view, not proof of a rendered frame or of every view path.
"""
import importlib.util
import json
from pathlib import Path
import time
import gdb


def tool_directory():
    return Path(tool_directory.__code__.co_filename).resolve().parent


DIRECTORY = tool_directory()
spec = importlib.util.spec_from_file_location('mif_view_validation', DIRECTORY / 'camera_capture.py')
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)
SITES = json.loads((DIRECTORY / 'camera_view_sites.json').read_text())
reg, memory, unpack, u64 = camera.reg, camera.memory, camera.unpack, camera.u64
ACTIVE = FINDER = SELECTED = LAST_OUTPUT = None


def vector(address):
    return list(unpack(address, 'ddd'))


def require_idle():
    if camera.ACTIVE or any(b.is_valid() and b.enabled for b in (gdb.breakpoints() or ())):
        raise ValueError('Use a fresh GDB session or stop/disable existing probes first')


def validate(base):
    validator = camera.Capture.__new__(camera.Capture)
    validator.game = base
    validator.validate()
    for site in SITES['sites'].values():
        expected = bytes.fromhex(site['bytes'])
        if memory(base + site['rva'], len(expected)) != expected:
            raise ValueError('View probe bytes differ at RVA 0x%x' % site['rva'])
    for rva, signature in SITES['guards'].items():
        expected = bytes.fromhex(signature)
        if memory(base + int(rva, 16), len(expected)) != expected:
            raise ValueError('View guard differs at RVA ' + rva)


def layout(base, controller):
    cvt = u64(controller)
    for slot, target in SITES['controller_slots'].items():
        if u64(cvt + int(slot, 16)) != base + target:
            raise ValueError('Unsupported controller slot ' + slot)
    manager = u64(controller + 0x350)
    mvt = u64(manager)
    for slot, target in SITES['manager_slots'].items():
        if u64(mvt + int(slot, 16)) != base + target:
            raise ValueError('Unsupported camera manager slot ' + slot)
    vector(controller + 0x310)
    vector(manager + 0x1368)
    return cvt, manager, mvt


def remove_finder():
    global FINDER
    if FINDER and FINDER.is_valid():
        FINDER.delete()
    FINDER = None


class Finder(gdb.Breakpoint):
    def __init__(self, base):
        super().__init__('*0x%x' % (base + SITES['sites']['find']['rva']), internal=True)
        self.base, self.silent = base, True

    def stop(self):
        global SELECTED
        try:
            controller = reg('rcx')
            cvt, manager, mvt = layout(self.base, controller)
            SELECTED = (gdb.selected_inferior().pid, self.base, controller, cvt, manager, mvt)
            gdb.write('Selected controller 0x%x, camera manager 0x%x.\n'
                      'Arm mif-view-trial LABEL, then continue.\n' % (controller, manager))
        except Exception as error:
            SELECTED = None
            gdb.write('View discovery rejected layout: %s\n' % error)
        gdb.post_event(remove_finder)
        return True


class Probe(gdb.Breakpoint):
    def __init__(self, capture, address):
        super().__init__('*0x%x' % address, type=gdb.BP_HARDWARE_BREAKPOINT, internal=True)
        self.capture, self.silent = capture, True
        if self.type != gdb.BP_HARDWARE_BREAKPOINT:
            self.delete()
            raise ValueError('Hardware execution breakpoint required; no software fallback')

    def stop(self):
        return self.capture.hit()


class Capture:
    def __init__(self, selected, output, label):
        self.pid, self.base, self.controller, self.cvt, self.manager, self.mvt = selected
        if self.pid != gdb.selected_inferior().pid:
            raise ValueError('Inferior changed; repeat mif-view-find')
        validate(self.base)
        if layout(self.base, self.controller) != (self.cvt, self.manager, self.mvt):
            raise ValueError('Controller/manager changed; repeat mif-view-find')
        self.label, self.rows, self.breakpoints = label, [], []
        self.ready = self.end = None
        self.recording = True
        self.file = open(output, 'x', encoding='utf-8')
        try:
            self.append({'event': 'capture_start', 'pid': self.pid, 'game_base': self.base,
                         'controller': self.controller, 'controller_vtable': self.cvt,
                         'manager': self.manager, 'manager_vtable': self.mvt,
                         'game_sha256': SITES['game_sha256'],
                         'candidate_sha256': camera.SITES['candidate_sha256'],
                         'validation': 'Exact live helper/probe/guard bytes, not a loaded-image hash',
                         'hardware_execution_sites': 1, 'preparation_seconds': 8,
                         'sample_seconds': 6, 'view_row_limit': 1200,
                         'note': 'Returned manager view only; GDB still perturbs timing. Buffered rows.'})
            self.breakpoints.append(Probe(self, self.base + SITES['sites']['view_return']['rva']))
        except Exception:
            self.finish('setup_error')
            raise

    def append(self, row):
        row.update(seq=len(self.rows), label=self.label, host_time=time.monotonic())
        self.rows.append(row)

    def hit(self):
        if not self.recording:
            return False
        try:
            # RCX survives the guarded leaf accessor and the remaining copies.
            if reg('rcx') != self.manager:
                return False
            if (u64(self.controller) != self.cvt or u64(self.controller + 0x350) != self.manager
                    or u64(self.manager) != self.mvt or reg('rax') != self.manager + 0x1350):
                raise ValueError('Controller/manager/cache identity changed; repeat discovery')
            now = time.monotonic()
            if self.ready is None:
                self.ready = now + 8
            if now < self.ready:
                return False
            if self.end is None:
                self.end = now + 6
                self.append({'event': 'sample_start'})
            rsp = reg('rsp')
            self.append({'event': 'view_return', 'thread': str(gdb.selected_thread().ptid),
                         'pc': reg('rip'), 'rsp': rsp, 'caller': u64(rsp + 0x28),
                         'controller': self.controller, 'manager': self.manager,
                         'control_rotation': vector(self.controller + 0x310),
                         'cache_stamp': unpack(self.manager + 0x1340, 'f')[0],
                         'cache_location': vector(self.manager + 0x1350),
                         'cache_rotation': vector(self.manager + 0x1368),
                         'returned_rotation': vector(reg('rdi'))})
            if len(self.rows) >= 1202:
                return self.request_finish('view_limit')
            if now >= self.end:
                return self.request_finish('timed')
        except Exception as error:
            self.append({'event': 'capture_error', 'error': str(error)})
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
            self.append({'event': 'capture_end', 'reason': reason})
            for row in self.rows:
                self.file.write(json.dumps(camera.clean(row), allow_nan=False) + '\n')
            self.file.close()
        if ACTIVE is self:
            ACTIVE = None
        gdb.write('View capture closed (%s); checkpoint removed and buffer saved.\n' % reason)


class Find(gdb.Command):
    """mif-view-find [GAME_BASE=$mif_base]: stop at a fresh controller view call."""
    def __init__(self):
        super().__init__('mif-view-find', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global FINDER, SELECTED
        if ACTIVE or FINDER:
            raise gdb.GdbError('Use mif-view-stop first')
        SELECTED = None
        try:
            require_idle()
            base = int(gdb.parse_and_eval(arg.strip() or '$mif_base'))
            validate(base)
            FINDER = Finder(base)
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Continue in on-foot gameplay; discovery stops at the next controller view call.\n')


class Trial(gdb.Command):
    """mif-view-trial LABEL: one hardware checkpoint, 8s prep, 6s sample, 1200 views."""
    def __init__(self):
        super().__init__('mif-view-trial', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global ACTIVE, LAST_OUTPUT
        label = arg.strip()
        if not label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in label):
            raise gdb.GdbError('Usage: mif-view-trial LABEL (letters/digits/_/-)')
        if ACTIVE or FINDER or not SELECTED:
            raise gdb.GdbError('Stop existing capture and complete mif-view-find first')
        output = '/tmp/mif-view-%s-%d.jsonl' % (label, time.time_ns())
        try:
            require_idle()
            ACTIVE = Capture(SELECTED, output, label)
            LAST_OUTPUT = output
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Continue: 8 seconds preparation, then 6 seconds sampling.\n'
                  'If running after about 20 seconds: Ctrl+C, mif-view-stop.\n' + output + '\n')


class Stop(gdb.Command):
    """mif-view-stop: remove this observer's checkpoint and save buffered rows."""
    def __init__(self):
        super().__init__('mif-view-stop', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        remove_finder()
        if ACTIVE:
            ACTIVE.finish()


class Export(gdb.Command):
    """mif-view-export: export fresh pointers, then detach for external polling."""
    def __init__(self):
        super().__init__('mif-view-export', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if arg.strip() or ACTIVE or FINDER or not SELECTED:
            raise gdb.GdbError('Complete mif-view-find and stop any trial before mif-view-export')
        try:
            pid, base, controller, cvt, manager, mvt = SELECTED
            if pid != gdb.selected_inferior().pid:
                raise ValueError('Inferior changed; repeat discovery')
            validate(base)
            if layout(base, controller) != (cvt, manager, mvt):
                raise ValueError('Object binding changed; repeat discovery')
            stat = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()
            row = {'event': 'view_binding', 'version': 1, 'pid': pid,
                   'start_ticks': int(stat[19]),
                   'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   'host_time': time.monotonic(), 'game_base': base,
                   'controller': controller, 'controller_vtable': cvt,
                   'manager': manager, 'manager_vtable': mvt,
                   'game_sha256': SITES['game_sha256'],
                   'candidate_sha256': camera.SITES['candidate_sha256'],
                   'note': 'Fresh validated pointers only; no trial or symptom reproduction.'}
            output = Path('/tmp/mif-view-binding-%d.json' % time.time_ns())
            with output.open('x') as file:
                file.write(json.dumps(row) + '\n')
            gdb.write(str(output) + '\nDetach and quit before running camera_pose_poll.py with this file.\n')
        except Exception as error:
            raise gdb.GdbError(str(error))


class Report(gdb.Command):
    """mif-view-report [FILE]: emit returned-view checkpoints and factual summary."""
    def __init__(self):
        super().__init__('mif-view-report', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            raise gdb.GdbError('Use mif-view-stop first')
        args = gdb.string_to_argv(arg)
        if len(args) > 1 or (not args and not LAST_OUTPUT):
            raise gdb.GdbError('Usage: mif-view-report [FILE]')
        spec = importlib.util.spec_from_file_location('mif_view_report', DIRECTORY / 'analyze_camera_view.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        gdb.write(module.report(Path(args[0] if args else LAST_OUTPUT)) + '\n')


Find()
Trial()
Stop()
Export()
Report()
gdb.write('View commands loaded; no probes installed. Use mif-camera-base, then mif-view-find.\n')
