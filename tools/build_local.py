#!/usr/bin/env python3
"""Build against the existing UE4SS dependencies without writing outside this mod."""
import argparse
from pathlib import Path
import re
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--sdk', type=Path, default=Path.home() / 'my_msvc/opt/msvc')
parser.add_argument('--ue4ss-root', type=Path, help='Existing UE4SS dependency/build tree for a standalone checkout')
parser.add_argument('--shutdown-diagnostic', action='store_true', help='Build bounded shutdown breadcrumbs as a separately named DLL')
parser.add_argument('--shutdown-fixture', action='store_true', help='Build the standalone DLL lifetime test fixture (no UE4SS import)')
parser.add_argument('--bridge-tests', action='store_true')
parser.add_argument('--camera-prototype', action='store_true', help='Build a separately named experimental native-camera DLL; never overwrite production')
parser.add_argument('--camera-tests', action='store_true', help='Build camera integration tests with production composition and no journal')
parser.add_argument('--camera-prototype-tests', action='store_true', help='Build standalone experimental camera integration tests')
parser.add_argument('--stage', type=int, choices=range(5), help='Cumulative diagnostic stage (default: src/DiagnosticStage.hpp)')
parser.add_argument('--evaluation-mode', choices=['reset', 'direct', 'trace'], help='Reset/generation (default), or Stage 1 direct/trace diagnostics')
parser.add_argument('--reset-tests', action='store_true', help='Build reset shim and generation integration tests')
parser.add_argument('--movement-tests', action='store_true', help='Build shipping movement handler and winner integration tests')
parser.add_argument('--evaluation-tests', action='store_true', help='Run the focused evaluation pass-through test build')
args = parser.parse_args()
if args.camera_tests and (args.camera_prototype or args.camera_prototype_tests or args.shutdown_diagnostic or
    args.shutdown_fixture or args.stage not in (None,4) or args.evaluation_mode not in (None,'reset')):
    parser.error('Production camera tests require stage 4/reset without diagnostic variants')
if args.camera_prototype_tests:
    args.camera_prototype = True
if args.camera_prototype and (args.shutdown_diagnostic or args.shutdown_fixture or args.stage not in (None,4) or
    args.evaluation_mode not in (None,'reset') or any([args.bridge_tests,args.reset_tests,args.movement_tests,args.evaluation_tests])):
    parser.error('Camera prototype is a separate stage 4/reset variant; select its own tests or DLL')
if args.shutdown_fixture:
    args.shutdown_diagnostic = True
if sum([args.bridge_tests, args.evaluation_tests, args.reset_tests, args.movement_tests, args.camera_tests]) > 1:
    parser.error('Select only one standalone test build')
if args.shutdown_fixture and any([args.bridge_tests, args.evaluation_tests, args.reset_tests, args.movement_tests]):
    parser.error('Select the shutdown fixture or an executable test, not both')
if args.evaluation_mode in ('direct', 'trace') and args.stage is None:
    args.stage = 1
if args.evaluation_mode in ('direct', 'trace') and args.stage != 1:
    parser.error('Direct/trace evaluation variants require Stage 1')
mod = Path(__file__).resolve().parents[1]
root = (args.ue4ss_root or mod.parents[1]).resolve()
out = mod / 'build'
out.mkdir(exist_ok=True)
# Reuse the configured UE4SS target's exact headers/defines, removing output paths.
metadata = root / 'Intermediates/.deps/MixedInputFix/windows/x64/Game__Shipping__Win64/cppmods/MixedInputFix/src/dllmain.cpp.obj.d'
text = metadata.read_text().split('    files =')[0]
flags = []
for value in re.findall(r'^\s*"((?:\\.|[^"\\])*)",?$', text, re.M):
    value = value.replace('\\"', '"').replace('\\\\', '\\')
    if value.startswith(('-I', '-D', '-external:I')):
        flags.append(value)
vc = sorted((args.sdk / 'vc/tools/msvc').iterdir())[-1]
kits = args.sdk / 'kits/10'
version = sorted((kits / 'include').iterdir())[-1].name
for directory in [vc / 'include', kits / 'include' / version / 'ucrt', kits / 'include' / version / 'shared', kits / 'include' / version / 'um']:
    flags += ['/imsvc' + str(directory)]
poly = next((root / 'Intermediates/.packages/p/polyhook_2/latest').glob('*/include/polyhook2/Detour/x64Detour.hpp')).parents[3]
flags += ['/I' + str(poly / 'include'), '/DASMJIT_STATIC', '/DZYDIS_STATIC_BUILD', '/DZYCORE_STATIC_BUILD']
# Do not inherit a previous stage from the parent target's cached metadata.
flags = [flag for flag in flags if not flag.startswith(('-DMIXED_INPUT_FIX_DIAGNOSTIC_STAGE', '/DMIXED_INPUT_FIX_DIAGNOSTIC_STAGE',
                                                      '-DMIXED_INPUT_FIX_EVALUATION_MODE', '/DMIXED_INPUT_FIX_EVALUATION_MODE',
                                                      '-DMIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC', '/DMIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC',
                                                      '-DMIXED_INPUT_FIX_DIAGNOSTICS', '/DMIXED_INPUT_FIX_DIAGNOSTICS'))]
flags = [flag for flag in flags if not flag.startswith(('-DMIXED_INPUT_FIX_CAMERA_PROTOTYPE','/DMIXED_INPUT_FIX_CAMERA_PROTOTYPE'))]
if args.camera_prototype:
    flags += ['/DMIXED_INPUT_FIX_CAMERA_PROTOTYPE=1']
if args.shutdown_diagnostic:
    if args.stage not in (None, 4) or args.evaluation_mode not in (None, 'reset'):
        parser.error('Shutdown diagnostic requires production stage 4/reset')
    flags += ['/DMIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC=1']
if args.stage is not None:
    flags += [f'/DMIXED_INPUT_FIX_DIAGNOSTIC_STAGE={args.stage}']
if args.evaluation_mode is not None:
    flags += [f'/DMIXED_INPUT_FIX_EVALUATION_MODE={dict(reset=0, direct=1, trace=2)[args.evaluation_mode]}']
is_test = args.bridge_tests or args.evaluation_tests or args.reset_tests or args.movement_tests or args.camera_prototype_tests or args.camera_tests
name = 'movement-tests' if args.movement_tests else 'reset-tests' if args.reset_tests else 'evaluation-tests' if args.evaluation_tests else ('bridge-tests' if args.bridge_tests else 'MixedInputFix')
if not is_test and args.evaluation_mode not in ('direct', 'trace'):
    name += '-production-candidate'
if not is_test and args.evaluation_mode == 'trace':
    name += '-stage1-trace'
if args.shutdown_diagnostic:
    name = name + '-shutdown' if is_test else 'MixedInputFix-shutdown-diagnostic'
if args.shutdown_fixture:
    name = 'shutdown-fixture'
if args.camera_tests:
    name = 'camera-tests'
if args.camera_prototype:
    name = 'camera-prototype-tests' if is_test else 'MixedInputFix-camera-prototype'
source = mod / ('tests/movement.cpp' if args.movement_tests else 'tests/reset.cpp' if args.reset_tests else 'tests/evaluation.cpp' if args.evaluation_tests else ('tests/bridges.cpp' if args.bridge_tests else 'src/dllmain.cpp'))
if args.shutdown_fixture:
    source = mod / 'tests/shutdown_fixture.cpp'
if args.camera_prototype_tests or args.camera_tests:
    source = mod / 'tests/camera_prototype.cpp'
command = ['clang-cl', '/nologo', '/c', '/std:c++latest', '/MD', '/O2', '/Zi', '/EHa', '/W4',
           '/FI' + str(mod / 'tools/clang_compat.hpp'),
           '/Fo' + str(out / (name + '.obj')), str(source), *flags]
subprocess.run(command, cwd=root, check=True)
extra_objects = []
if args.shutdown_diagnostic and not is_test:
    entry_object = out / 'shutdown-entry.obj'
    subprocess.run(['clang-cl', '/nologo', '/c', '/std:c++latest', '/MD', '/O2', '/Zi', '/GS-',
                    '/Fo' + str(entry_object), str(mod / 'src/ShutdownEntry.cpp'), *flags], cwd=root, check=True)
    extra_objects = [str(entry_object), '/entry:mif_shutdown_entry']
libs = [vc / 'lib/x64', kits / 'lib' / version / 'ucrt/x64', kits / 'lib' / version / 'um/x64',
        root / 'Binaries/Game__Shipping__Win64/UE4SS', poly / 'lib']
product = out / (name + ('.exe' if is_test else '.dll'))
command = ['lld-link', '/nologo', *([] if is_test else ['/dll']), '/machine:x64', '/debug:full', '/incremental:no',
           '/out:' + str(product), '/pdb:' + str(out / (name + '.pdb')),
           '/implib:' + str(out / (name + '.lib')), str(out / (name + '.obj')),
           *extra_objects,
           *['/libpath:' + str(p) for p in libs], *([] if is_test or args.shutdown_fixture else ['UE4SS.lib']), 'PolyHook_2.lib', 'asmjit.lib', 'asmtk.lib',
           'Zydis.lib', 'Zycore.lib', 'kernel32.lib', 'user32.lib', 'advapi32.lib', 'psapi.lib']
subprocess.run(command, cwd=out, check=True)

# Shipping DLLs should not expose the local build-machine path through CodeView.
# Sanitize only the embedded PDB path after linking; executable code is untouched.
if not is_test and name == 'MixedInputFix-production-candidate':
    import struct

    image = bytearray(product.read_bytes())
    pe = struct.unpack_from('<I', image, 0x3C)[0]
    coff = pe + 4
    section_count = struct.unpack_from('<H', image, coff + 2)[0]
    optional_size = struct.unpack_from('<H', image, coff + 16)[0]
    optional = coff + 20
    section_table = optional + optional_size

    debug_rva, debug_size = struct.unpack_from('<II', image, optional + 112 + 6 * 8)

    def rva_to_raw(rva):
        for i in range(section_count):
            entry = section_table + i * 40
            virtual_size, virtual_address, raw_size, raw_pointer = struct.unpack_from(
                '<IIII', image, entry + 8
            )
            span = max(virtual_size, raw_size)
            if virtual_address <= rva < virtual_address + span:
                return raw_pointer + (rva - virtual_address)
        raise RuntimeError(f'CodeView RVA 0x{rva:X} is not mapped by any PE section')

    sanitized = False
    if debug_rva and debug_size:
        debug_raw = rva_to_raw(debug_rva)
        for i in range(debug_size // 28):
            entry = debug_raw + i * 28
            debug_type = struct.unpack_from('<I', image, entry + 12)[0]
            data_size = struct.unpack_from('<I', image, entry + 16)[0]
            data_raw = struct.unpack_from('<I', image, entry + 24)[0]

            if debug_type != 2 or image[data_raw:data_raw + 4] != b'RSDS':
                continue

            path_start = data_raw + 24
            path_end = image.find(b'\0', path_start, data_raw + data_size)
            if path_end < 0:
                raise RuntimeError('CodeView PDB path is not NUL terminated')

            replacement = (name + '.pdb').encode('utf-8')
            capacity = path_end - path_start
            if len(replacement) > capacity:
                raise RuntimeError('Sanitized CodeView PDB name does not fit original field')

            image[path_start:path_end] = replacement + b'\0' * (capacity - len(replacement))
            sanitized = True

    if not sanitized:
        raise RuntimeError('Could not locate CodeView RSDS record in production DLL')

    product.write_bytes(image)

if args.shutdown_fixture:
    host = out / 'shutdown-host.obj'
    subprocess.run(['clang-cl', '/nologo', '/c', '/std:c++latest', '/MD', '/O2', '/Zi',
                    '/Fo' + str(host), str(mod / 'tests/shutdown_host.cpp'), *flags], cwd=root, check=True)
    subprocess.run(['lld-link', '/nologo', '/machine:x64', '/out:' + str(out / 'shutdown-host.exe'), str(host),
                    *['/libpath:' + str(p) for p in libs], 'kernel32.lib'], cwd=out, check=True)
print(product)
print(f'Diagnostic stage: {args.stage if args.stage is not None else "source default (src/DiagnosticStage.hpp)"}')
print(f'Evaluation mode: {args.evaluation_mode or "source default (reset/generation)"}')
