"""GDB: bounded shutdown ordering/fault capture, armed immediately before exit.

No inferior calls or input probes. Only two PE detach entrypoints and MIF's
exported uninstall are observed, plus their actual return addresses. SIGSEGV
stays stopped for the user; it is never swallowed or automatically continued.
"""
import json
from pathlib import Path
import struct
import gdb

ACTIVE = None


def memory(address, size):
    return bytes(gdb.selected_inferior().read_memory(address, size))


def u32(address):
    return struct.unpack('<I', memory(address, 4))[0]


def u64(address):
    return struct.unpack('<Q', memory(address, 8))[0]


def reg(name):
    return int(gdb.parse_and_eval('$' + name))


def modules():
    maps = Path(f'/proc/{gdb.selected_inferior().pid}/maps').read_text()
    found = {}
    for line in maps.splitlines():
        parts = line.split(maxsplit=5)
        if len(parts) != 6 or int(parts[2], 16):
            continue
        path = parts[5].lower()
        key = ('mif' if path.endswith('/mixedinputfix/dlls/main.dll') else
               'ue4ss' if path.endswith('/ue4ss.dll') else
               'game' if path.endswith('/oblivionremastered-win64-shipping.exe') else None)
        if not key:
            continue
        base = int(parts[0].split('-')[0], 16)
        if memory(base, 2) != b'MZ':
            continue
        pe = base + u32(base + 0x3C)
        if memory(pe, 6) != b'PE\0\0\x64\x86' or memory(pe + 24, 2) != b'\x0b\x02':
            raise ValueError('Unexpected PE architecture')
        if key in found:
            raise ValueError('Ambiguous module base: ' + key)
        found[key] = {'base': base, 'entry': base + u32(pe + 40), 'pe': pe, 'path': parts[5]}
    if set(found) != {'mif', 'ue4ss', 'game'}:
        raise ValueError('Cannot identify all three modules; return info proc mappings')
    return found, maps


def export(module, wanted):
    base = module['base']
    export_rva = u32(module['pe'] + 136)
    export_size = u32(module['pe'] + 140)
    if not export_rva or export_size < 40:
        raise ValueError('Missing export directory')
    directory = base + export_rva
    count = u32(directory + 24)
    if not 0 < count <= 4096:
        raise ValueError('Invalid export count')
    functions, names, ordinals = (base + u32(directory + offset) for offset in (28, 32, 36))
    for i in range(count):
        address = base + u32(names + i * 4)
        name = bytearray()
        for j in range(128):
            ch = memory(address + j, 1)
            if ch == b'\0':
                break
            name.extend(ch)
        if name.decode('ascii') == wanted:
            ordinal = struct.unpack('<H', memory(ordinals + i * 2, 2))[0]
            if ordinal >= u32(directory + 20):
                raise ValueError('Invalid export ordinal')
            target = u32(functions + ordinal * 4)
            if not target or export_rva <= target < export_rva + export_size:
                raise ValueError('Null or forwarded export cannot be probed')
            return base + target
    raise ValueError('Missing export: ' + wanted)


class ReturnProbe(gdb.Breakpoint):
    def __init__(self, capture, name):
        self.capture, self.name = capture, name
        self.ptid = gdb.selected_thread().ptid
        self.rsp = reg('rsp') + 8
        super().__init__(f'*0x{u64(reg("rsp")):x}', internal=True)

    def stop(self):
        if gdb.selected_thread().ptid != self.ptid or reg('rsp') != self.rsp:
            return False
        self.enabled = False
        return self.capture.emit(self.name + '_return', rax=reg('rax'))


class EntryProbe(gdb.Breakpoint):
    def __init__(self, capture, name, address, detach=False):
        self.capture, self.name, self.detach = capture, name, detach
        super().__init__(f'*0x{address:x}', internal=True)
        if detach:
            self.condition = '$edx == 0'

    def stop(self):
        cap = self.capture
        if cap.emit(self.name + '_enter', rcx=reg('rcx'), rdx=reg('rdx'), r8=reg('r8'),
                    backtrace=gdb.execute('bt 12', to_string=True)):
            return True
        cap.probes.append(ReturnProbe(cap, self.name))
        return False


class Capture:
    def __init__(self, path):
        self.modules, maps = modules()
        uninstall = export(self.modules['mif'], 'uninstall_mod')
        self.file = open(path, 'x')
        self.probes, self.count = [], 0
        try:
            self.emit('armed', modules=self.modules, maps=maps)
            for key in ('mif', 'ue4ss'):
                self.probes.append(EntryProbe(self, key + '_detach', self.modules[key]['entry'], True))
            self.probes.append(EntryProbe(self, 'uninstall', uninstall))
            gdb.events.stop.connect(self.on_stop)
            gdb.events.exited.connect(self.on_exit)
        except Exception:
            self.close()
            raise

    def emit(self, event, **fields):
        if self.count >= 32:
            return True
        self.count += 1
        thread = gdb.selected_thread()
        self.file.write(json.dumps(dict(seq=self.count, event=event,
                                       thread=thread.ptid if thread else None, **fields)) + '\n')
        self.file.flush()
        if self.count == 32:
            for probe in self.probes:
                probe.enabled = False
            gdb.write('Shutdown event limit reached; run mif-exit-stop.\n')
            return True
        return False

    def on_stop(self, event):
        if isinstance(event, gdb.SignalEvent):
            # Snapshot the actual live patch bytes as well as the fault. Return
            # addresses and old crash offsets alone do not identify hook lifetime.
            patches = {}
            for rva, size in ((0x392B6A6, 5), (0x3934891, 6), (0x392CD15, 6),
                              (0x489D2F9, 5), (0x488A0E9, 5), (0x488AC3C, 5),
                              (0x488AD32, 5), (0x488AE2C, 5), (0x488AF22, 5)):
                try:
                    patches[hex(rva)] = memory(self.modules['game']['base'] + rva, size).hex()
                except gdb.MemoryError:
                    patches[hex(rva)] = 'unreadable'
            self.emit('signal_stop', signal=event.stop_signal,
                      registers=gdb.execute('info registers', to_string=True),
                      backtrace=gdb.execute('bt 20', to_string=True), patches=patches)
            gdb.write('Shutdown signal captured; inferior remains stopped. Inspect before continuing.\n')

    def on_exit(self, event):
        self.emit('process_exited', exit_code=getattr(event, 'exit_code', None))
        self.close()

    def close(self):
        global ACTIVE
        for probe in self.probes:
            if probe.is_valid():
                probe.delete()
        gdb.events.stop.disconnect(self.on_stop)
        gdb.events.exited.disconnect(self.on_exit)
        self.file.close()
        if ACTIVE is self:
            ACTIVE = None


class Arm(gdb.Command):
    def __init__(self):
        super().__init__('mif-exit-arm', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        global ACTIVE
        args = gdb.string_to_argv(arg)
        if ACTIVE or len(args) != 1:
            raise gdb.GdbError('Usage: mif-exit-arm NEW_JSONL_PATH (one active capture)')
        try:
            ACTIVE = Capture(args[0])
        except Exception as error:
            raise gdb.GdbError(str(error))
        gdb.write('Armed 3 shutdown entry probes, maximum 32 events. Continue, then close normally.\n')


class Stop(gdb.Command):
    def __init__(self):
        super().__init__('mif-exit-stop', gdb.COMMAND_USER)

    def invoke(self, arg, from_tty):
        if ACTIVE:
            ACTIVE.close()


Arm()
Stop()
