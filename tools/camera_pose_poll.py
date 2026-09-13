"""Read control/cache pose through /proc/PID/mem without attaching or stopping.

The source view trace supplies candidate pointers only. Revalidate them in the
same running process. These asynchronous snapshots are not rendered frames.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import time

DIRECTORY = Path(__file__).resolve().parent
SITES = json.loads((DIRECTORY / 'camera_view_sites.json').read_text())


def process_identity(pid):
    root = Path('/proc') / str(pid)
    stat = (root / 'stat').read_text().rsplit(')', 1)[1].split()
    status = (root / 'status').read_text().splitlines()
    tracer = int(next(line.split(':', 1)[1] for line in status if line.startswith('TracerPid:')))
    if tracer or stat[0] in ('T', 't', 'Z', 'X'):
        raise ValueError('Target is traced, stopped or exited; detach GDB before polling')
    return {'pid': pid, 'start_ticks': int(stat[19]),
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


class Memory:
    def __init__(self, pid):
        self.fd = os.open('/proc/%d/mem' % pid, os.O_RDONLY | os.O_CLOEXEC)

    def read(self, address, size):
        if address <= 0 or not 0 < size <= 4096:
            raise ValueError('Invalid bounded memory read')
        data = os.pread(self.fd, size, address)
        if len(data) != size:
            raise ValueError('Short process-memory read')
        return data

    def close(self):
        os.close(self.fd)


def u64(read, address):
    return struct.unpack('<Q', read(address, 8))[0]


def object_identity(read, address):
    data = read(address, 24)
    # Vtable, UObject internal index and class. Object flags may change normally.
    return (data[:8] + data[12:24]).hex()


def validate(read, source):
    base = source['game_base']
    for site in SITES['sites'].values():
        expected = bytes.fromhex(site['bytes'])
        if read(base + site['rva'], len(expected)) != expected:
            raise ValueError('Live view code differs')
    for rva, signature in SITES['guards'].items():
        expected = bytes.fromhex(signature)
        if read(base + int(rva, 16), len(expected)) != expected:
            raise ValueError('Live view guard differs at ' + rva)
    controller, manager = source['controller'], source['manager']
    if u64(read, controller + 0x350) != manager:
        raise ValueError('Controller/manager binding changed; source pointers are stale')
    for kind, obj in [('controller', controller), ('manager', manager)]:
        vt = u64(read, obj)
        if vt != source[kind + '_vtable']:
            raise ValueError('Stale ' + kind + ' vtable')
        for slot, target in SITES[kind + '_slots'].items():
            if u64(read, vt + int(slot, 16)) != base + target:
                raise ValueError('Unsupported ' + kind + ' virtual target')
    return [object_identity(read, controller), object_identity(read, manager)]


def snapshot(read, source, identities):
    controller, manager = source['controller'], source['manager']
    def check():
        if ([object_identity(read, controller), object_identity(read, manager)] != identities
                or u64(read, controller + 0x350) != manager):
            raise ValueError('Object identity/binding changed; stop and rediscover')
    check()
    start = time.monotonic_ns()
    control_before = read(controller + 0x310, 24)
    cache_before = read(manager + 0x1340, 64)
    control_after = read(controller + 0x310, 24)
    cache_after = read(manager + 0x1340, 64)
    end = time.monotonic_ns()
    check()
    def decode(control, cache):
        return {'control_rotation': list(struct.unpack('<3d', control)),
                'cache_stamp': struct.unpack_from('<f', cache)[0],
                'cache_location': list(struct.unpack_from('<3d', cache, 0x10)),
                'cache_rotation': list(struct.unpack_from('<3d', cache, 0x28))}
    return {'event': 'pose_sample', 'read_start_ns': start, 'read_end_ns': end,
            'read_span_ns': end - start,
            'repeated_bytes_equal': control_before == control_after and cache_before == cache_after,
            'before': decode(control_before, cache_before), 'after': decode(control_after, cache_after),
            'control_before_hex': control_before.hex(), 'control_after_hex': control_after.hex(),
            'cache_before_hex': cache_before.hex(), 'cache_after_hex': cache_after.hex()}


def clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return repr(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    return value


def source_header(path):
    with path.open() as file:
        row = json.loads(file.readline())
    if not (row.get('event') == 'view_binding' and row.get('version') == 1 or
            row.get('event') == 'capture_start' and row.get('hardware_execution_sites') == 1):
        raise ValueError('Expected a mif-view-export binding or original camera-view JSONL trace')
    if row.get('game_sha256') != SITES['game_sha256']:
        raise ValueError('Source trace shipping version differs')
    return row


def run(args):
    source = source_header(args.source)
    pid = source['pid']
    try:
        identity = process_identity(pid)
    except FileNotFoundError:
        raise ValueError('Source game process has exited; export a fresh binding once with mif-view-export') from None
    if source['event'] == 'view_binding' and any(source[k] != identity[k] for k in ('start_ticks', 'boot_id')):
        raise ValueError('Source process incarnation differs; export a fresh binding')
    start_seconds = identity['start_ticks'] / os.sysconf('SC_CLK_TCK')
    if not start_seconds <= source['host_time'] <= time.monotonic():
        raise ValueError('Source predates this process or has incompatible host time; rediscover')
    # Reject original files from an earlier boot. This and live byte/object
    # checks are guards, not a lifetime guarantee for pointers in old traces.
    boot_epoch = int(next(line.split()[1] for line in Path('/proc/stat').read_text().splitlines()
                          if line.startswith('btime ')))
    if args.source.stat().st_mtime < boot_epoch:
        raise ValueError('Source file predates this boot; rediscover')
    memory = Memory(pid)
    try:
        identities = validate(memory.read, source)
        if process_identity(pid) != identity:
            raise ValueError('Process changed during setup')
        if args.check_only:
            print('Validated live process, object bindings, view code and slots; no capture started.')
            return 0
        output = Path('/tmp/mif-pose-poll-%s-%d.jsonl' % (args.label, time.time_ns()))
        rows = []
        def append(row):
            row.update(seq=len(rows), host_time=time.monotonic(), label=args.label)
            rows.append(row)
        with output.open('x') as file:
            append({'event': 'capture_start', **identity, 'game_base': source['game_base'],
                    'controller': source['controller'], 'manager': source['manager'],
                    'object_identities': identities, 'source': str(args.source),
                    'source_sha256': hashlib.sha256(args.source.read_bytes()).hexdigest(),
                    'game_sha256': SITES['game_sha256'],
                    'validation': 'Live view/control code and object slots; no full live DLL hash',
                    'sample_hz': args.hz, 'sample_seconds': args.seconds, 'prep_seconds': args.prep,
                    'note': 'Read-only external polling; no ptrace attach, signals, breakpoints or inferior calls.'})
            reason, failed = 'timed', False
            print(str(output), flush=True)
            print('%gs preparation, then %gs sampling at %g Hz. Ctrl+C saves the buffer.' %
                  (args.prep, args.seconds, args.hz), flush=True)
            try:
                time.sleep(args.prep)
                append({'event': 'sample_start'})
                deadline = time.monotonic()
                end, period = deadline + args.seconds, 1 / args.hz
                while time.monotonic() < end:
                    if process_identity(pid) != identity:
                        raise ValueError('Process identity changed')
                    row = snapshot(memory.read, source, identities)
                    now = time.monotonic()
                    # Skip missed deadlines instead of adding a burst of reads.
                    skipped = max(0, int((now - deadline) / period))
                    row['skipped_deadlines'] = skipped
                    append(row)
                    deadline += (skipped + 1) * period
                    time.sleep(max(0, min(end, deadline) - time.monotonic()))
            except KeyboardInterrupt:
                reason = 'user_stop'
            except Exception as error:
                reason, failed = 'read_or_identity_error', True
                append({'event': 'capture_error', 'error': str(error)})
            finally:
                append({'event': 'capture_end', 'reason': reason})
                for row in rows:
                    file.write(json.dumps(clean(row), allow_nan=False) + '\n')
            print('Saved %d samples; %s. Repeated reads do not prove atomicity or rendered frames.' %
                  (sum(r['event'] == 'pose_sample' for r in rows), reason))
            return int(failed)
    finally:
        memory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Fresh mif-view-export binding, or view trace from the same running game')
    parser.add_argument('--label', default='X-oppose')
    parser.add_argument('--hz', type=float, default=20)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--prep', type=float, default=8)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    if (not 1 <= args.hz <= 50 or not 1 <= args.seconds <= 60 or not 0 <= args.prep <= 30
            or not args.label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.label)):
        parser.error('Use 1..50 Hz, 1..60 seconds, 0..30 prep, and a letters/digits/_/- label')
    try:
        return run(args)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
