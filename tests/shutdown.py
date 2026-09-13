"""Windows DLL lifecycle and observer regressions, using synthetic game memory."""
from pathlib import Path
import importlib.util
import os
import shutil
import struct
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('report', root / 'tools/shutdown_report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)
out = Path(tempfile.mkdtemp(prefix='lifecycle-', dir=root / 'build/shutdown'))
env = dict(os.environ, WINEPREFIX=str(root / 'build/shutdown/wine-prefix'), WINEDEBUG='-all')
for mode in ('unload', 'pinned', 'terminate'):
    dll = out / f'{mode}.dll'
    shutil.copyfile(root / 'build/shutdown-fixture.dll', dll)
    windows_path = 'Z:' + str(dll).replace('/', '\\')
    with (out / f'{mode}.log').open('w') as log:
        subprocess.run(['wine', str(root / 'build/shutdown-host.exe'), windows_path, mode],
                       env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=45)
    data = Path(str(dll) + '.shutdown.bin').read_bytes()
    lines = report.decode(data)
    text = '\n'.join(lines)
    (out / f'{mode}.report.txt').write_text(text + '\n')
    assert 'uninstall_enter a=0x1234 b=0x5678' in text
    if mode == 'terminate':
        assert 'dll_detach' not in text and 'destructor_body_end' not in text
    else:
        assert text.index('dll_detach_enter') < text.index('destructor_body_end') < text.index('dll_detach_return')
        expected = 'a=0x0' if mode == 'unload' else 'a=0x1'
        assert expected in next(line for line in lines if 'dll_detach_enter' in line)
        assert 'b=0x1' in next(line for line in lines if 'dll_detach_return' in line)
    if mode == 'pinned':
        assert 'commit_result a=0x1 b=0x0' in text
        assert text.index('resume_end') < text.index('commit_result') < text.index('dll_detach_enter')
        assert 'bridge_destructor' not in text and 'unwind_begin' not in text
    print(f'PASS: {mode} lifecycle, published records, CRT ordering')

# Interrupted record and capacity overflow must be explicit, never decoded as
# completed phases or silently treated as a complete journal.
partial = bytearray(data)
struct.pack_into('<I', partial, 64, 0)
assert 'INCOMPLETE SLOT' in '\n'.join(report.decode(partial))
struct.pack_into('<I', partial, 20, 129)
assert 'OVERFLOW' in report.decode(partial)[-1]
try:
    report.decode(data[:-1])
    raise AssertionError('truncated capture accepted')
except ValueError:
    pass
print('PASS: incomplete, overflow and truncated journal detection')

for name in ('bridge-tests-shutdown', 'reset-tests', 'movement-tests'):
    with (out / f'{name}.log').open('w') as log:
        subprocess.run(['wine', str(root / 'build' / f'{name}.exe')], env=env, cwd=root,
                       stdout=log, stderr=subprocess.STDOUT, check=True, timeout=45)
    print((out / f'{name}.log').read_text().strip())
print(f'Evidence: {out}')
