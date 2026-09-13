# Normal-exit investigation — 2026-09-07

**Status updated 2026-09-08: intermittent, awaiting another reproduction.** The first diagnostic live trial and a subsequent production session exited cleanly. Shutdown no longer blocks the [camera investigation](camera-capture.md). Preserve this tooling for the next naturally occurring failure; no speculative production shutdown change is justified.

New work is in `~/OblivionRemastered-MixedInputFix`. The original project `/path/to/UE4SS/cppmods/MixedInputFix` supplies matching baseline source and existing dependencies; it was not edited. Installed game/mod files were inspected, not modified. The pre-existing README change and `development-history.md.save` were left alone.

## SHUTDOWN: established evidence

The original project DLL, installed `main.dll`, and preserved workspace `build/MixedInputFix-production-candidate.dll` all hash to `7551c3af9193e2556af7671fbac9b6f0458753f8271430db1fac7e182a21830c`. Workspace source initially matched the original project's source exactly.

### Clean live baseline — 2026-09-08

The user reports an hours-long session with diagnostic DLL SHA-256 `65f7a6d9f86c1c3eb5528f15044bd37d5ca5cd33ac676b1d928b6381b27e4c50`, closed through the normal in-game quit menu, with no Unreal crash reporter. The preserved binary at `build/shutdown/live-pi5RyQ/exit.shutdown.bin` was decoded again and matches both the saved report and the user's transcript:

```text
MIFEXIT1 pid=348 reserved=4/128
module=0x6fffee6e0000 game=0x140000000 bridge=0x13fff0000 installation=0x2c95560
001 tid=352 opened a=0x0 b=0x0
002 tid=352 installed a=0x9 b=0x0
003 tid=352 dll_detach_enter a=0x1 b=0x0
004 tid=352 dll_detach_return a=0x1 b=0x1
```

Evidence SHA-256:

```text
eb87f7aab6595b3e76aab7573761411c0cc28c39295a454c16688218eb62cafa  exit.shutdown.bin
c7860bbd016edd194ea1007bb0754b729ec224b56eeb9fd8c46a2c4cda626bef  exit.report.txt
```

On this clean run, explicit `uninstall_mod` was not observed, patch restoration did not run, process/CRT detach was entered, and the full CRT detach returned successfully. No unexpected bridge/unwind/trampoline destruction was recorded. These observations apply to this run; they do not establish the ordering in the earlier crash.

After preserving the evidence, the user restored the exact production candidate (`7551c3af9193e2556af7671fbac9b6f0458753f8271430db1fac7e182a21830c`). A subsequent hours-long production session exited cleanly using Alt+F4. Duration, exit method, and absence of a crash reporter are user-reported; the journal and workspace DLL hashes were independently checked.

| Run | Established outcome |
|---|---|
| Earlier production session | Normal shutdown crash; saved dump has `IsRequestingExit=true` and game-code invalid virtual-call fault at RVA `0x66581D8` |
| Diagnostic, hours long, in-game menu exit | Clean; four-event journal above |
| Restored production candidate, hours long, Alt+F4 | Clean, per user report |

The failure is intermittent. These clean runs do not show that the diagnostic fixed it, Alt+F4 avoids it, menu exit or session length causes it, or CRT detach is faulty. Keep the diagnostic DLL/PDB, journal, and debugger tools for another naturally occurring failure. Preserve that run's available dump, logs and journal/debugger evidence separately and compare against this baseline. The production candidate does not generate a new shutdown journal; an old journal beside it is not evidence from the new session. Unless independent static analysis finds new concrete evidence, proceed with camera capture without further shutdown trials.

### Actual successful-production lifetime

1. `start_mod` constructs `MixedInputFixMod`. A temporary `unique_ptr<Installation>` prepares bridges, registers unwind tables and records original bytes. Before publishing patches, `GetModuleHandleExW(FROM_ADDRESS | PIN)` pins MIF. Successful publication releases the unique pointer into deliberately retained raw `installation` storage.
2. **If** UE4SS calls `uninstall_mod`, `delete mod` calls the derived destructor. It disables overrides and calls `commit(false)`. After the derived body returns, the imported `CppUserModBase` destructor, member destruction and deleting destructor/deallocation still execute. The base destructor can access UE4SS GUI/input infrastructure; MIF registers neither GUI tabs nor key bindings.
3. Restoration collects other-thread handles, suspends captured threads, rejects RIPs inside patch intervals, verifies current patch bytes, makes all nine ranges writable, copies originals, flushes the instruction cache, restores protections, then resumes threads through RAII. Order: reset, winner, dispatch, two camera getters, four movement getters. Cache-flush failure rolls bytes back. Conflicts/suspension failures decline restoration. Protection failures are reported separately.
4. **Successful installation is never deleted**, even after restoration fails. Bridge code, both six-byte CALL slots and both dynamic unwind tables remain allocated/registered. Production creates **no PolyHook evaluation trampoline**. The bridge/unwind/free destructors apply to failed preparation or standalone local test objects, not ordinary successful-production uninstall.
5. Winner/dispatch returns are at the original six-byte boundaries; reset/getter returns remain at original five-byte boundaries. Retained storage permits already-running callbacks to return after restoration. Existing standalone tests establish those local contracts, not Unreal shutdown safety. No callback captures the mod object.
6. Provenance and dispatch-pointer TLS are constant-initialized, trivially destructible storage with no user-defined TLS exit cleanup. There is no evaluation-entry wrapper, worker thread or asynchronous MIF callback. Disabled getters still call vanilla CommonInput; reset and dispatch still call original game targets. Code retention does not establish the lifetime of those callers or Unreal objects.
7. The linked production PDB contains CRT/library teardown, including the header-defined `RC::Output::DefaultTargets::default_devices` vector destructor at MIF RVA `0x1330`. MIF does not populate that local vector. Its existence is a reason to observe the full CRT detach, not evidence it is faulty. Production has no custom DllMain.

Restoration is not a global callback drain. The thread snapshot does not certify that no new thread can appear afterward, and the current thread is not suspended. These limits do not establish the reported cause. No shutdown synchronization redesign is justified by this audit.

### Installed UE4SS ordering

Installed UE4SS differs from the local build. Installed SHA-256: `1f42db9b6f61a7d1790d9576af43a924bf47cb134deea77c2babde216f4ff5e7`. Its installed PDB GUID `{194881DB-9732-4679-98E8-A929CB3AED4D}`, age 2, matches the PE CodeView record. Binary inspection corroborates the relevant source path:

- UE4SS DllMain detach calls `static_cleanup` (RVA `0x60A200`).
- Cleanup invokes `UE4SSProgram::~UE4SSProgram` (`0x5E7540`), which closes output devices and destroys the mod-wrapper vector. This is not an explicit `uninstall_mods()` call.
- `CppMod::~CppMod` (`0x4FA780`) calls `FreeLibrary` and `RemoveDllDirectory`, without calling MIF's exported uninstall. Explicit reinstall/uninstall is a different path.
- MIF pinning prevents ordinary FreeLibrary unload. It does **not** suppress eventual process-detach/CRT teardown, establish dependency destruction order or retain engine objects.

Binary excerpts and resolved destructor calls are in `build/shutdown/`. Broad disassembly excerpts may contain trailing unrelated instructions; the named function/call sites are the evidence. Win32 documents [pinning until termination](https://learn.microsoft.com/en-us/windows/win32/api/libloaderapi/nf-libloaderapi-getmodulehandleexw), [process-detach constraints](https://learn.microsoft.com/en-us/windows/win32/dlls/dllmain), and CRT initialization/destruction ordering (`https://learn.microsoft.com/en-us/cpp/build/run-time-library-behavior?view=msvc-170`). Process termination can leave heaps/locks inconsistent after other threads terminate. No cleanup was moved into DllMain and pinning was not removed.

### Existing exit dump, separate from the new test

A saved report from **September 7, 18:43:24 America/Boise**, after 7592 seconds, has `IsRequestingExit=true`. The faulting thread is `OblivionThread`, Windows thread 1204. Its exception context establishes:

```text
Exception = 0xC0000005
RIP = 0x1466581D8 (game RVA 0x66581D8)
instruction = FF 90 58 03 00 00 = call qword ptr [rax+0x358]
RAX = 0x1E30C0140
RCX = RBX = 0x15928E480
invalid read = 0x1E30C0498 = RAX+0x358
```

The reported stack contains game code through the game thread entry and kernel32, without MIF uninstall, bridges, UE4SS detach or CRT frames. MIF's dump image timestamp `0x6A9F2134` and size `0x12A000` match the validated candidate. CodeView information is absent; this is supporting identity evidence, not a loaded-image hash. The user's September 8 update confirms the earlier production shutdown crash; `IsRequestingExit` independently establishes exit context. Original XML/dump were copied unchanged into `build/shutdown/existing-crash/`, with a bounded summary.

**Inference, not cause:** invalid native object/vtable state during the game's exit path is the most directly evidenced failure class. Earlier MIF behavior, mod interaction or state left behind could still cause it. The dump does not identify who invalidated the object, whether the object concerns input, or whether MIF cleanup happened earlier. Treat MIF as implicated by the user's enabled/disabled isolation.

Immediate bridge/slot/unwind/trampoline freeing during successful MIF uninstall is less supported because that freeing path is absent. Loader-lock/CRT/dependency order remains a viable alternative. Evidence does not justify further ranking or a production change, especially a movement workaround.

## Exact diagnostic instrumentation

`--shutdown-diagnostic` builds a separately named **stage 4/reset** DLL with the same nine hooks and original branches. Source from `action_info` through `movement_y`, all of `Bridges::build`, and `Provenance.hpp`, `Sites.hpp`, `DiagnosticStage.hpp` remain byte-identical to the baseline (`build/shutdown/gameplay-source-audit.txt`). No input helper calls the new recorder.

- Startup creates an **8192-byte** `main.dll.shutdown.bin` beside the loaded DLL using CREATE_NEW, maps it, and retains mapping/handles until termination. It refuses to overwrite earlier evidence.
- At most **128 fixed records** contain sequence, event, Windows thread ID and two numeric arguments. Atomic reservation and final sequence publication identify incomplete records. Shutdown recording performs only bounded memory operations and a Win64 TEB thread-ID read: no file I/O/flush, CRT/UE4SS logger, allocation, ordinary TLS helper, loader call, wait or exception interception.
- Events bracket exported uninstall/delete, derived destructor, disable, restoration collection/suspension/validation/write/flush/protection/resume, result/exception, and any unexpected bridge/unwind/trampoline destruction.
- A separate diagnostic `/GS-` entry translation unit forwards all arguments/results to the existing `_DllMainCRTStartup`. It records process-detach entry and return around the **entire CRT routine**, including static destructors. Attach/thread notifications pass through without recording. The compiled wrapper has no pre-initialization security-cookie dependency and no added calls besides the original CRT entry (`build/shutdown/entry.asm`).
- `uninstall_delete_complete` is after `delete mod`, including imported base/member destruction and deallocation. A debugger return probe, rather than that marker alone, establishes execution of the exported RET.
- `tools/shutdown_report.py` decodes without editing evidence. Persistence is OS-backed, not a power-loss durability guarantee. Local Wine tests confirm visibility after normal and forced termination. Missing/incomplete evidence alone cannot prove a path did not run.

The first pass does not count in-flight gameplay callbacks or log runtime input. Conditional debugger capture below can establish fault-time code state and ordering if needed.

## Preserved artifact and repeat procedure

The first live test is complete; the procedure below is retained for a future reproduction. It is not a prerequisite for camera work.

```text
~/OblivionRemastered-MixedInputFix/build/MixedInputFix-shutdown-diagnostic.dll
SHA-256 65f7a6d9f86c1c3eb5528f15044bd37d5ca5cd33ac676b1d928b6381b27e4c50
```

Matching PDB: `build/MixedInputFix-shutdown-diagnostic.pdb`. Hash manifest: `build/shutdown/SHA256SUMS`. Original DLL/PDB are preserved under their original names in workspace `build/` and remain unchanged in the original project.

**With the game fully closed**, run these commands. They back up the installed DLL and any earlier journal. Do not hot-reload/reinstall mods in a running game: that exercises a different path.

```bash
cd ~/OblivionRemastered-MixedInputFix
mif_dll_dir='/path/to/SteamLibrary/steamapps/common/Oblivion Remastered/OblivionRemastered/Binaries/Win64/ue4ss/mods/MixedInputFix/dlls'
mif_trial_dir="$(mktemp -d "$PWD/build/shutdown/live-XXXXXX")"
printf '%s\n' "$mif_trial_dir" > build/shutdown/last-live-dir.txt
cp -- "$mif_dll_dir/main.dll" "$mif_trial_dir/before-main.dll"
if [ -f "$mif_dll_dir/main.dll.shutdown.bin" ]; then
    mv -- "$mif_dll_dir/main.dll.shutdown.bin" "$mif_trial_dir/previous.shutdown.bin"
fi
cp -- build/MixedInputFix-shutdown-diagnostic.dll "$mif_dll_dir/main.dll"
sha256sum "$mif_dll_dir/main.dll"
```

Launch with the same other mods/layout, load the usual save, play briefly to reach the normal gameplay state, then close through **the same normal exit action that failed**. No special camera-conflict trial is needed. Record exit method, duration and whether the crash reporter appeared. If a short session exits cleanly but failure followed a long session, preserve the clean result before a representative-duration repeat.

Before closing, `main.dll.diagnostic.log` should contain these new/current-launch lines, followed by the existing installation-success lines:

```text
[MixedInputFix] Shutdown observer ready: main.dll.shutdown.bin (128 records)
[MixedInputFix] Production stage 4 selected: reset CALL/generation; dispatch-only scopes
```

If it says `Shutdown observer UNAVAILABLE`, this launch lacks new breadcrumbs. With the game closed, archive the old binary journal/check permissions and relaunch. Observer failure does not deliberately change input behavior. The text log appends across launches; the binary file is new per trial.

After exit/crash-report generation, collect in a terminal:

```bash
cd ~/OblivionRemastered-MixedInputFix
mif_dll_dir='/path/to/SteamLibrary/steamapps/common/Oblivion Remastered/OblivionRemastered/Binaries/Win64/ue4ss/mods/MixedInputFix/dlls'
mif_trial_dir="$(cat build/shutdown/last-live-dir.txt)"
cp -- "$mif_dll_dir/main.dll.shutdown.bin" "$mif_trial_dir/exit.shutdown.bin"
cp -- "$mif_dll_dir/main.dll.diagnostic.log" "$mif_trial_dir/main.dll.diagnostic.log"
cp -- "$mif_dll_dir/../../../UE4SS.log" "$mif_trial_dir/UE4SS.log"
python3 tools/shutdown_report.py "$mif_trial_dir/exit.shutdown.bin" | tee "$mif_trial_dir/exit.report.txt"
```

Also preserve the new `CrashContext.runtime-xml` and `UEMinidump.dmp` together from the relevant new folder under:

```text
/path/to/SteamLibrary/steamapps/compatdata/2623190/pfx/drive_c/users/steamuser/Documents/My Games/Oblivion Remastered/Saved/Crashes/
```

Return the binary journal, decoded report, both logs, new crash files if any, and exit method/duration. Keep the earlier archived crash separate.

### Exact expected output

Addresses/PID/thread IDs vary. A pinned normal process-detach path bypassing explicit uninstall is expected to produce:

```text
MIFEXIT1 pid=... reserved=4/128
module=0x... game=0x... bridge=0x... installation=0x...
001 tid=... opened a=0x0 b=0x0
002 tid=... installed a=0x9 b=0x0
003 tid=... dll_detach_enter a=0x1 b=0x0
004 tid=... dll_detach_return a=0x1 b=0x1
```

For detach, **any nonzero `a` means process termination**, zero means explicit unload/failed load; return `b` is the CRT BOOL result. Relative order with UE4SS detach remains to be observed. If explicit uninstall occurs, its successful sequence is:

```text
uninstall_enter           a=mod pointer, b=caller return address
destructor_enter          a=1 if owning installation, b=this
overrides_disabled
restore_begin             a=9
collect_begin             a=9
collect_end               a=1
pause_begin
pause_end                 a=1
bytes_checked             a=9
pages_writable            a=9 b=9
bytes_written             a=9
cache_flushed             a=1
protections_restored      a=1 b=0
resume_begin              a=paused threads, b=handles
resume_end                a=paused threads, b=failed ResumeThread calls
commit_result             a=1 b=0
destructor_body_end
uninstall_delete_complete
```

There should be no bridge/unwind/trampoline destruction after successful publication. `restore_rejected.a` identifies a conflicting patch RVA. Fewer writable pages, failed cache flush/rollback, failed commit, protection warnings, resume failures or `restore_exception` require investigation. Failure `b` at collection/pause may contain GetLastError, but RIP-conflict rejection does not set a fresh error; do not mistake stale error state for cause.

| Result | Implication, with limits |
|---|---|
| Crash after `installed`, no cleanup/detach event | With complete evidence and a game-code fault, supports **D: an earlier game shutdown/state path**. Forced termination/lost evidence can also omit detach. It does not exonerate earlier MIF behavior. |
| Uninstall/restoration begins but does not complete | **A possible:** last event bounds the interval. Another thread could have crashed concurrently; obtain fault context/thread before assigning cause. |
| Derived body ends but delete does not complete | Focus imported UE4SS base/member destruction/deallocation and concurrent faults (**A/C boundary**). Restoration already returned. |
| Successful commit and delete complete, then crash | **B possible:** stale/in-flight state after explicit cleanup; other later faults remain possible. Inspect fault-time patches/mappings. Completion alone does not prove MIF caused the later fault. |
| Detach enters but does not return | Focus MIF CRT/static/dependency teardown or a concurrent fault (**C**). This does not imply bridge destruction occurred. |
| Both detach records, then crash | MIF's CRT routine returned. Inspect later module teardown and retained code/data/engine state (**B/C/D**). |
| Bridge/unwind/free event after successful publication | Unexpected for retained installation; compare its address with the journal bridge and capture the destruction stack. |
| Diagnostic exits cleanly | Intermittent/timing/build-layout-sensitive failure remains possible. Preserve evidence and compare representative repeats; do not promote it as a fix. |
| Missing header/file, partial slot, overflow | Incomplete instrumentation evidence; resolve before inferring ordering. |

## Conditional debugger capture

Use if the first journal/dump leaves ordering/fault ambiguous. `tools/shutdown_capture.py` finds actual mapped game/MIF/UE4SS PE bases and the uninstall export. It observes **three entrypoints**, conditional on process detach for the two PE entries, plus their actual thread/RSP-matched returns. Maximum **32 events**. Stopped signals record registers, a bounded current-thread backtrace and all nine live patch byte sequences. It calls no inferior functions and changes no input values. Software breakpoints perturb timing.

Arm immediately before normal exit in a fresh GDB session:

```bash
cd ~/OblivionRemastered-MixedInputFix
pgrep -af '[O]blivionRemastered-Win64-Shipping\.exe'
gdb -q -nx
```

```gdb
set pagination off
set print thread-events off
set debuginfod enabled off
set auto-solib-add off
handle SIGUSR1 nostop noprint pass
handle SIGSEGV stop print pass
handle SIGABRT stop print pass
attach PID
source tools/shutdown_capture.py
mif-exit-arm /tmp/mif-exit-order-01.jsonl
continue
```

Substitute the actual PID; use a fresh JSONL filename each repeat. If ptrace is denied, quit the unattached debugger and use `sudo gdb -q -nx`. Expect `Armed 3 shutdown entry probes, maximum 32 events. Continue, then close normally.` Entry/return probes auto-continue; signals remain stopped. At a fault preserve the JSONL and run:

```gdb
info registers
bt 20
x/12i $pc
info proc mappings
```

Return that output plus the JSONL/journal. Wine SIGSEGV may be a handled first-chance exception, not necessarily fatal. After preserving a relevant stop, `continue` passes the signal to normal handling for crash-report generation. If manually stopped or capped, use `mif-exit-stop`, `detach`, `quit`; after inferior exit just `quit`. If exit/probes do not arrive in about 30 seconds, interrupt and preserve the stack instead of waiting indefinitely.

`ue4ss_detach_enter → uninstall_enter` on the same thread would establish uninstall inside the observed UE4SS loader entry interval. `uninstall_return` proves execution beyond the in-DLL marker. A fault before either detach entry excludes those observed cleanup intervals on that run. Concurrent event order alone does not prove causality.

## CAMERA: read-only findings and next capture

No camera behavior, manifest or camera probe code changed. Established: max-magnitude arbitration selects a signed winner (later mapping wins ties); action modifiers can subsequently change the scalar; dispatch is inside the binding loop; getters choose the native path per dispatch; latest X/Y samples `+D64/+D68` and response factors `+D60/+D5C` are shared/retained across calls. Source-specific processing occurs before the final output calls. Policy-0 opposing candidates do not simply sum to zero; magnitude/quantization are not source classifiers.

Inference only: sign/source transitions, modifier history, shared response state, repeated outputs or downstream consumption may explain the axis-local stall. The exact mechanism remains unknown. No global priority, raw-value sum, mouse-path forcing, handler duplication or state-clearing workaround is justified.

The shutdown evidence is preserved and the exact original candidate has been restored. If a future shutdown trial replaces it, close the game and restore it before using the existing camera observer:

```bash
cd ~/OblivionRemastered-MixedInputFix
mif_dll_dir='/path/to/SteamLibrary/steamapps/common/Oblivion Remastered/OblivionRemastered/Binaries/Win64/ue4ss/mods/MixedInputFix/dlls'
cp -- build/MixedInputFix-production-candidate.dll "$mif_dll_dir/main.dll"
sha256sum "$mif_dll_dir/main.dll"
```

Expected hash `7551c3af9193e2556af7671fbac9b6f0458753f8271430db1fac7e182a21830c`. Do not weaken camera helper signatures to accept the shutdown DLL.

Follow [camera-capture.md](camera-capture.md): fresh GDB attach as above, `source tools/camera_capture.py`, `mif-camera-base`. Six bounded trials: `01-X-stick`, `02-X-mouse`, `03-Y-stick`, `04-Y-mouse`, `05-X-same`, `06-X-oppose`. Each uses:

```gdb
mif-camera-trial 01-X-stick
continue
# After automatic stop:
mif-camera-stop
mif-camera-report
```

Each has 8 seconds preparation, 3 seconds recording, maximum 6000 rows, both axes observed. Review the first isolated report before proceeding. Opposing-X combines moderate native right stick right with continuous true mouse/gyro left of slowly varying strength. Preserve each unique raw JSONL and summary. Release-order/Y-opposition controls follow only if needed.

Existing probes already observe winner/source, mapping/final values, CommonInput before getter, actual getter result/branch, dispatch identity/multiplicity, latest axes/gains before/after, output receiver/target and bounded receiver changes. They do not establish consumer accumulation from arithmetic trace sums.

| First divergence | Next bounded investigation |
|---|---|
| Nonzero winner suppressed after action modifiers | Active modifier chain and sign-transition history. |
| Getter/branch disagrees with verified winner/snapshot | Camera provenance/fallback and final-value format; movement unchanged. |
| Nonzero input, suitable branch, suppressed native output | Shared axes/gains, then the specifically implicated response/gate code. |
| Opposing processed outputs or cross-evaluation sign alternation | Actual target stores/consumer; trace sums alone do not establish cancellation. |
| Healthy output but stalled camera | `x/32i ACTUAL_TARGET` from the trace, then only accumulator store/read/reset probes. |

## Tests, signatures and files

- Diagnostic DLL/PDB and lifecycle fixture built. Five pre-existing UE4SS-header warnings; no remaining diagnostic compile errors.
- All **28** shipping signatures match executable SHA-256 `b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`. Signature manifest unchanged.
- Actual Wine DLL tests passed: explicit unload, pinned process exit, forced termination without detach; CRT bracketing; last-error preservation; retained published bridges/unwind data. Partial/overflow/truncated journal decoding passed.
- Bridge tests with diagnostic compiled passed, including transactional restoration and in-flight dispatch unhook. Reset ABI/register/unwind/in-flight tests, full movement integration tests, and host provenance tests passed.
- Existing camera/movement observer regressions passed. New shutdown export/forwarder, return-thread/RSP and event-cap regressions passed; actual GDB script sourcing passed. These local tests do not certify the real UE4SS/Unreal shutdown order; the clean live observation is recorded separately above.

Rebuild/test commands:

```bash
python3 tools/build_local.py --ue4ss-root /path/to/UE4SS --shutdown-diagnostic
python3 tools/build_local.py --ue4ss-root /path/to/UE4SS --shutdown-fixture
python3 tools/build_local.py --ue4ss-root /path/to/UE4SS --bridge-tests --shutdown-diagnostic
python3 tools/build_local.py --ue4ss-root /path/to/UE4SS --reset-tests
python3 tools/build_local.py --ue4ss-root /path/to/UE4SS --movement-tests
python3 tests/shutdown.py
python3 tests/shutdown_capture.py
python3 tests/camera_capture.py
python3 tests/movement_capture.py
c++ -std=c++20 -Wall -Wextra -Werror -pthread tests/provenance.cpp -o build/provenance-tests
build/provenance-tests
```

Lifecycle evidence: `build/shutdown/lifecycle-5fzmc7sj/`; build/PE/signature/source audit: `build/shutdown/`. Rebuilds may change PE timestamp/hash; use the supplied artifact for this trial.

Changed: `src/dllmain.cpp` (shutdown probes), `tools/build_local.py` (diagnostic/fixture outputs and external dependency root), this guide and priority notices in the camera/reference docs. Added: `src/ShutdownDiagnostic.hpp`, `src/ShutdownEntry.cpp`, `tools/shutdown_report.py`, `tools/shutdown_capture.py`, `tests/shutdown.py`, `tests/shutdown_fixture.cpp`, `tests/shutdown_host.cpp`, `tests/shutdown_capture.py`. Generated files are under ignored `build/`.

**No production shutdown/camera fix, and no movement architecture/behavior change.** The next evidence is the bounded camera baseline and opposing-X captures. Shutdown awaits another naturally occurring failure.
