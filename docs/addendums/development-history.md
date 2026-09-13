> **Historical record:** This document preserves the development state as it
> changed over time. Older sections describe superseded implementations and
> should not be read as documentation of the current mod. References to
> `build/` artifacts, logs, checkpoints, captures, PDBs, and disassemblies refer
> to local development material that is not included in the public repository
> unless stated otherwise.

Current movement candidate (2026-09-07): **per-action winning-mapping provenance — Live Verified** by the user on 2026-09-07. The remaining task is same-axis opposing native right-stick and real mouse/gyro camera input. See [CAMERA_CAPTURE_GUIDE.md](../guides/camera-capture.md) for the bounded observation procedure. No production changes are made for this investigation.

DLL: `build/MixedInputFix-production-candidate.dll`
SHA-256: `7551c3af9193e2556af7671fbac9b6f0458753f8271430db1fac7e182a21830c`
Matching PDB: `build/MixedInputFix-production-candidate.pdb`.

The user live-validated this exact candidate: W/S/A/D work, the Backward/Left regression is fixed, fractional analog movement stays smooth, and native left-stick movement works during real mouse/gyro activity. Full cardinal stick can win the observed opposing-digital exact 1.0 tie; fractional stick loses to digital 1.0. Two digital directions beat opposite diagonal stick components on both axes because those components are fractional. Other mixed arbitration behaved as predicted; no movement regression was observed in normal gameplay.

The preceding raw capture campaign established the movement mechanism. The four NOPs caused positive digital A/S activation to be overwritten to zero; signed left-stick values require precisely the split those NOPs forced. Magnitude arbitration and later-mapping exact ties determine ownership independently for each action. CommonInput can flip without changing those winners. Action modifiers can change magnitude after selection. Detailed **Live Verified / Static Analysis / Inference** evidence is in [MOVEMENT_CAMERA_REVIEW.md](../reference/movement-and-camera.md).

Production now leaves all four original `75 0F` movement branches intact and redirects their existing five-byte getter CALLs. A verified digital winner returns 0; a verified corresponding LeftX/LeftY winner returns 1; Unknown or failed validation calls the original CommonInput getter. No values, caches, merge policy, mapping order, modifiers or global input-type fields are rewritten.

| Direction | Redirected getter CALL | Intact original branch |
|---|---|---|
| Backward | `0x488AC3C` | `0x488AC43` |
| Forward | `0x488AD32` | `0x488AD39` |
| Left | `0x488AE2C` | `0x488AE33` |
| Right | `0x488AF22` | `0x488AF29` |

Digital classification uses the already-resolved physical FKey metadata: matching full eight-byte identity, digital type 0, Axis1D mapped result and finite nonnegative winning contribution. It supports rebound digital keys without a WASD whitelist or captured numeric FName IDs. Signed movement requires runtime identity equality with the engine's LeftX/LeftY globals and 1D key metadata. Button-axis, other analog keys, unreadable/mismatched metadata, unsupported mapped types or policies, foreign callers, stale generations and invalid dispatch identities fall back to vanilla. Movement Digital/LeftStick tags are distinct from camera Mouse/Gamepad tags. The provenance tag is retained through action modifiers rather than inferred again from the dispatched value.

The existing reset CALL, generation/TLS table, winner-store replay, synchronous dispatch scope, camera getter behavior, transaction and uninstall architecture remain. Production still installs nine patches: reset, winner, dispatch, two camera getter CALLs, four movement getter CALLs. There is no evaluation entry detour or movement NOP in production. Reset-mode diagnostic stages 0–3 now leave movement vanilla; stage 4 enables the six getter redirects. Explicit historical Stage 1 direct/trace modes retain their diagnostic NOPs; their previously built DLLs are unchanged.

Validation passed: 28 exact shipping signatures; host provenance suite; Windows movement, reset, bridge and historical evaluation suites under Wine; Python observer tests; actual GDB `source` and `mif-move-report` without `__file__`; final DLL export and targeted linked-code audit. The new movement suite executes complete shipping movement handlers (external object/subsystem lookups stubbed), the shipping magnitude/tie comparison and the installed winner/getter bridges. It covers all directions, rebound identities, fractional axes, action-modified magnitudes, independent action ownership, exact ties in both mapping orders, fallback, camera isolation, null subsystem, dispatch unwind and in-flight movement getter uninstall returning at original +5. These checks establish standalone behavior; the user’s subsequent live results above establish movement acceptance. Rebinding, focus/reconnect and every gameplay mode are not individually attested by this latest report.

The observer now resolves both companion files from its compiled source filename under GDB, accepts either the baseline NOPs or restored branches, and records CommonInput RCX **before** the getter CALL because the redirected helper may clobber volatile RCX. New captures also expose physical-key metadata. Raw old captures remain readable and unchanged.

[Focused live validation and GDB commands](../guides/movement-capture.md). Audit (`build/movement-production/audit.txt`). Build log (`build/movement-production/build.log`). Movement tests (`build/movement-production/movement-tests.log`). Shipping signatures (`build/movement-production/signatures.txt`).

Reproduce:

```sh
python tools/build_local.py --stage 4
python tools/build_local.py --movement-tests
python tools/build_local.py --reset-tests
python tools/build_local.py --bridge-tests
python tools/build_local.py --evaluation-tests
c++ -std=c++20 -Wall -Wextra -Werror -pthread tests/provenance.cpp -o build/provenance-tests
build/provenance-tests
python tests/movement_capture.py
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/movement-tests.exe
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/reset-tests.exe
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/bridge-tests.exe
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/evaluation-tests.exe
```

The original NOP candidate (`0a945b1c…a053`) and pre-edit source/tests/tools/docs are preserved in `build/movement-nop-checkpoint/`. All 17 raw session captures are copied to `build/movement-production/`; inventory and hashes (`build/movement-production/capture-inventory.txt`). Parent-tree modifications are untouched.

The following is the historical NOP-candidate record. Its “current,” pending-capture and movement-NOP descriptions are superseded by the status above.

---

Current production candidate (2026-09-06): **reset CALL / generation provenance**, now successfully extended-live-tested by the user, with two known limitations below. Artifact: `build/MixedInputFix-production-candidate.dll`. The five-argument Stage 1 trace has now been live-confirmed to reach the main menu with both entry and successful-return markers. Together with the matched GDB fifth-argument values, this confirms the omitted work-list argument as the cause of the preceding four-argument trace startup crash.


First extended live production validation succeeded: main-menu startup, native analog left-stick movement together with real mouse/gyro, native right-stick camera, mouse/gyro camera, freestanding gameplay, swimming, horseback, menus, and swapping save files. The original mixed-input failure is fixed in normal gameplay. Native controller movement works in all directions.

**Priority 1 — keyboard movement regression:** keyboard Forward and Right work, but Backward and Left do not. The failure follows logical directions across rebinding. Keyboard/controller combinations also have unexpected direction-dependent behavior: with A and D held, straight analog left/backward can work while down-left can fail. This observation does not establish the mechanism. The four unconditional movement NOPs are **not production-correct**; the earlier description of them as proven is withdrawn. Diagnose all four directional handlers and propose a source-aware replacement before changing the production implementation or DLL. Preserve vanilla digital movement, true analog magnitude, and the working reset/generation camera architecture.

**Priority 2 — simultaneous right-stick + gyro:** simultaneous native right-stick and mouse/gyro camera inputs both appear to influence the camera. Compatible directions generally behave acceptably, but opposing directions on the same axis can briefly seize/stall that axis; the other axis remains unaffected. The underlying value/dispatch/state mechanism has not yet been captured. This observation does not establish whether Enhanced Input combines values, dispatches multiple actions/bindings, or leaves branch-specific camera state active.

The user's thumb-touch-gated Steam Controller gyro configuration naturally avoids most simultaneous camera inputs, but this is not sufficient for release. Always-on gyro and coarse stick movement plus gyro correction are supported use cases to pursue. Diagnosis must preserve X/Y independently and allow the engine's intended same-direction composition or predictable opposing-direction resolution; no global mouse/gamepad priority is assumed. The working candidate is preserved while diagnostic evidence is collected. Codex has not installed anything automatically.

Current diagnosis and proposed replacement: [MOVEMENT_CAMERA_REVIEW.md](../reference/movement-and-camera.md). Backward/Left initially store the negated digital input, but the NOPs force an overwrite with `min(original_input, 0)`, zeroing positive digital activation. Forward/Right use `max(original_input, 0)` and survive. The smallest proposed replacement restores the original branches and routes four movement getter CALLs using verified dispatch source/value-format provenance. Mixed keyboard/stick mapping arbitration needs live capture before implementation. A bounded observer, `tools/movement_capture.py`, records that evidence against the unchanged DLL; exact sites and commands are in the review. Production source and DLL have not been rebuilt or changed in this diagnosis pass.

For the next live session, use [MOVEMENT_CAPTURE_GUIDE.md](../guides/movement-capture.md): attach/base validation, SIGUSR1 handling, one trial at a time, an 8-second preparation delay, 3-second sparse capture capped at 900 event rows, and a pasteable report capped at 150 lines. Start with W only. Camera stall investigation and production changes remain deferred until movement evidence is reviewed.

Production no longer uses an evaluation-entry lifetime wrapper. The `evaluate` scoped wrapper and `current_evaluation` stack pointer have been removed. Stage 4 is now the source default and uses reset/generation mode. Historical Stage 1 direct and scope-free five-argument trace diagnostics remain explicitly selectable; their validated DLLs are unchanged. The former `scoped` mode is replaced by `reset`.

| Production site (RVA) | Installed behavior |
|---|---|
| Evaluation entry `0x392B630` | Unmodified; no entry detour/trampoline prepared in production |
| **Reset CALL `0x392B6A6`** | Original five-byte `E8 rel32` redirected to near assembly shim; tail-jumps to original reset `0x3939FA0`, which returns to the existing `0x392B6AB` |
| Winner `0x3934891` | Retained six-byte `FF 15 disp32` CALL; bridge saves volatile state, records with owner/frame/generation checks, replays the winning store once, returns to `0x3934897` |
| Dispatch `0x392CD15` | Retained six-byte `FF 15 disp32` CALL; leaf adapter passes binding/instance plus R13 owner and RBP evaluation frame to the synchronous scoped wrapper; original virtual target executes once and returns to `0x392CD1B` |
| Horizontal getter `0x489D2F9` | Five-byte CALL to near leaf adapter and generation-aware getter |
| Vertical getter `0x488A0E9` | Five-byte CALL to near leaf adapter and generation-aware getter |
| Movement `0x488AC43`, `0x488AD39`, `0x488AE33`, `0x488AF29` | Four unconditional two-byte NOPs; keyboard Backward/Left regression confirmed |

Nine patches total. Both original camera `cmp al,1` instructions at `0x489D2FE` / `0x488A0EE` remain intact, as does original CommonInput getter `0x2E6CC30`. All original 15 validation signatures and transaction/uninstall safeguards remain; a 30-byte owner-setup signature at `0x392B650` is added. All 16 match the shipping executable. The reset CALL's existing signature already covers its original target displacement.

The reset shim uses `pushfq; sub rsp,0x260`, preserving RAX/RCX/RDX/R8–R11 and a 16-aligned FXSAVE64 image containing x87, XMM0–15 and MXCSR. Its helper home area and all saves lie below incoming RSP. It clears DF for the helper, restores FX/GPR state and flags/RSP, then uses a register-preserving indirect tail jump to the original reset. No game home slot, stack argument, or return address is overwritten. Nonvolatile GPRs remain untouched by the shim and are preserved by the helper ABI. Three dynamic unwind entries cover the body/prologue, POPFQ and tail jump. The emitted shim is 131 bytes plus an eight-byte target; the final DLL's bookkeeping helper is a 158-byte scalar leaf with no calls, allocation, loops, logging, initialization guard or AVX instructions. Audit: `build/production-audit.txt`; disassemblies: `build/reset-shim-disassembly.txt`, `build/reset-generation-disassembly.txt`, `build/reset-generation-linked-disassembly.txt`.

Bookkeeping resets a persistent `constinit thread_local` 128-entry table in constant time by clearing its count, advances a 64-bit generation, and records owner/frame. It validates `RBP == reset-entry-RSP + 0x108`, derived from the existing evaluation frame. Winner recording reads the saved evaluation RBP at mapping `[rbp+0x37]`, validates owner/frame, captures a generation token, and rechecks the token on record. Foreign/unknown mappings replace earlier known winners with Unknown; broken/mismatched evaluation identity invalidates the table. Overflow and invalid identities disable overrides; generation-number exhaustion permanently disables that thread, preventing token reuse.

A nested reset discards the outer generation. Existing outer dispatches and resumed outer winners fall back; no outer evaluation table is restored. Only synchronous dispatch has a scope. Every dispatch, including Unknown or mismatched, masks its parent. Getters require the active dispatch's generation, frame, action and instance to match current valid provenance, revalidate Axis1D/max policy, and reject a replaced/Unknown snapshot. Without a valid dispatch, stale records cannot override vanilla CommonInput. There is no evaluation return thunk or return-address substitution.

Validation passed:

- Host provenance: reset/rollover, nested same/different-owner invalidation, stale tokens including reused frame addresses, replacement/Unknown, instance/axis checks, dispatch masking/unwind, no-dispatch fallback, thread isolation, invalid frames and capacity overflow.
- New Windows reset suite: all GPRs, RFLAGS including DF, XMM0–15/x87/MXCSR, RSP, home/stack slots, return address and return values compared against direct reset; a stress helper clobbers volatile GPR/XMM/x87/MXCSR state. Original reset executes once. Dynamic unwind succeeds at every shim instruction boundary. Actual reset CALL install/execute and in-flight restoration return at original +5. Corrupted reset/owner signatures reject before bridge allocation. Recorder, nested dispatch/reset, action/type/policy, stale-generation and vanilla fallback integration checks pass.
- Existing Windows bridge suite: winner/store/registers, unwind, dispatch once, getter fallback, C++/SEH dispatch cleanup, stages 0–4, transactional restore and six-byte in-flight dispatch-unhook regression.
- Retained direct/five-argument trace Windows suite: now executes the first 62 shipping bytes to include the newly validated owner setup; keeps fifth-header dereference, stack/TLS preservation and trampoline verification coverage.
- All 16 shipping signatures, Windows x64 exports `start_mod` / `uninstall_mod`, and Python tool syntax verified. DLL build has five existing UE4SS-header warnings; standalone builds each have one existing CRT deprecation warning. Wine's unrelated graphics/configuration warnings did not prevent successful execution.

Reproduce the candidate and tests:

```sh
python tools/build_local.py --stage 4
python tools/build_local.py --reset-tests
python tools/build_local.py --bridge-tests
python tools/build_local.py --evaluation-tests
c++ -std=c++20 -Wall -Wextra -Werror -pthread tests/provenance.cpp -o build/provenance-tests
build/provenance-tests
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/reset-tests.exe
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/bridge-tests.exe
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/evaluation-tests.exe
```

Candidate DLL: `build/MixedInputFix-production-candidate.dll`. SHA-256: `0a945b1ce600abe54de83bc1ba9f37df55149cbe051d97d109157f07bd95a053`. Matching PDB: `build/MixedInputFix-production-candidate.pdb`. Build log: `build/production-build.log`. Test logs: `build/reset-tests.log`, `build/bridge-tests.log`, `build/evaluation-tests.log`. Shipping validation: `build/production-signatures.txt`. Prior source/tests/tools/docs and build files were checkpointed under `build/five-argument-confirmed-checkpoint/`; the trace DLL hash remains `a8ccce4816ea032e17b943158b680c68147f604188ee5c7c99a5edc7a536d836` and direct DLL hash remains `f8aac2c35fbc90f982be8c7e657983b6982755039ce61eea79b047cbbc4729e6`.

Changed files: `src/dllmain.cpp`, `src/Provenance.hpp`, `src/Sites.hpp`, `src/DiagnosticStage.hpp`, `tests/reset.cpp` (new), `tests/provenance.cpp`, `tests/bridges.cpp`, `tests/evaluation.cpp`, `tools/build_local.py`, `README.md`, `CALLING_CONTRACT_REVIEW.md`, plus local build/audit artifacts. Parent-tree work remains untouched.

Remaining live checks: keyboard movement and mixed keyboard/analog cache semantics; simultaneous opposing camera inputs and their value/dispatch/state sequence; direct reset-to-winner frame and vertical dispatch-chain capture; reconnect/focus changes. Startup, separate camera sources, movement plus mouse/gyro, gameplay modes, menus and save swapping have now passed user testing. Nested work intentionally sacrifices overrides on stale outer generations. Standalone/Wine tests do not establish every live mitigation or game path. Existing thread-enumeration/hot-patching limitations remain. **Nothing was installed into Oblivion.**

The following is the preserved historical diagnostic and implementation record. Its old live status, defaults, hashes and scoped-production descriptions are superseded by the candidate status above.

---

Current confirmation build (2026-09-06): **five-argument Stage 1 trace**, built and standalone-tested; **not installed or live-tested**. The DLL for the next live test is **`build/MixedInputFix-stage1-trace.dll`**, not the unchanged `build/MixedInputFix.dll` direct artifact.

The user live-confirmed argument five on the same invocation: `[rsp+0x20]` at caller VA `0x14383AEAC` and `[rbp+0x560]` at evaluation VA `0x14392D294` both held `0x1492801F8`. Its header contained data pointer `0x13E2BE480` and packed fields `0x0000000400000000`, consistent with Num=0 / Max=4. This confirms the forwarding requirement identified in [CALLING_CONTRACT_REVIEW.md](../reference/calling-contract.md). The prior trace's WriteFile call zeroed its outgoing fifth slot without restoring the game argument, explaining a concrete invalid-read path; the exact live fault instruction remains uncaptured.

The corrected Windows x64 prototype is:

```cpp
using Evaluate = void (*)(void* owner, void* components, float delta,
                          bool paused, void* work_list);
void evaluate_trace(void* owner, void* components, float delta,
                    bool paused, void* work_list);
```

`work_list` stays opaque and is forwarded unchanged, with no hardcoded game pointer. The diagnostic constructs no provenance/TLS scopes. It keeps the once-only entry and successful-return markers, the four movement NOPs and the evaluation detour; winner, dispatch and both camera getter hooks remain disabled. The retained scoped source wrapper also received the shared prototype/forwarding correction, solely for consistency; it is not selected by this DLL and is not the proposed final architecture.

The **linked DLL** audit establishes: six pushes and `sub rsp,0x58` put wrapper RSP at entry-RSP−0x88; `mov rbx,[rsp+0xB0]` saves the incoming fifth argument before diagnostics. Nonvolatile RBX survives those calls. Both the first-entry and already-logged paths execute `mov [rsp+0x20],rbx` immediately before calling the trampoline. The callee therefore receives argument five at entry-RSP+0x28. WriteFile uses the wrapper's own outgoing area below its entry RSP; its null lpOverlapped cannot overwrite any original incoming stack argument. Return diagnostics use that same local area after the game returns. Full explanation and checked instruction locations: `build/evaluation-five-argument-audit.txt`; object and final DLL disassembly: `build/evaluation-five-argument-trace-disassembly.txt` and `build/evaluation-five-argument-trace-linked-disassembly.txt`.

Validation passed: focused Windows evaluation suite, existing Windows bridge suite, and host provenance suite. The focused synthetic body executes the first 32 shipping bytes, loads argument five through `[rbp+0x560]`, and dereferences header fields at +0/+8/+12. It tests an empty Num=0/Max=4 header and a changing nonempty header across first-entry/return diagnostics and repeated calls, checks caller fifth/sixth stack slots after return, untouched provenance TLS, movement NOPs, null winner/dispatch slots, and unchanged inactive signatures. The bridge suite now forwards and dereferences a non-null fifth pointer through the retained scoped recursion test and keeps its C++/SEH coverage. Exactly one trace entry and one normal-return marker appeared in the focused run (`build/five-argument-diagnostics.log`). DLL exports `start_mod` and `uninstall_mod` verified. DLL build: five existing UE4SS-header warnings; each standalone build: one existing CRT deprecation warning. Wine completed successfully despite unrelated graphics/configuration warnings.

Reproduce:

```sh
python tools/build_local.py --stage 1 --evaluation-mode trace
python tools/build_local.py --evaluation-tests
python tools/build_local.py --bridge-tests
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/evaluation-tests.exe
WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/bridge-tests.exe
c++ -std=c++20 -Wall -Wextra -Werror -pthread tests/provenance.cpp -o build/provenance-tests
build/provenance-tests
```

Output DLL: `build/MixedInputFix-stage1-trace.dll`. SHA-256: `a8ccce4816ea032e17b943158b680c68147f604188ee5c7c99a5edc7a536d836`. Matching PDB: `build/MixedInputFix-stage1-trace.pdb`. Logs: `build/stage1-trace-build.log`, `build/evaluation-build.log`, `build/evaluation-tests.log`, `build/bridge-build.log`, `build/bridge-tests.log`. Previous trace DLL/PDB/object, test artifacts, logs and the pre-edit source/docs are preserved under `build/four-argument-trace-checkpoint/`. The direct DLL remains byte-identical (SHA-256 `f8aac2c35fbc90f982be8c7e657983b6982755039ce61eea79b047cbbc4729e6`).

Files changed in this confirmation pass: `src/dllmain.cpp`, `tests/evaluation.cpp`, `tests/bridges.cpp`, `README.md`, `CALLING_CONTRACT_REVIEW.md`, plus local build/audit artifacts. No production redesign was implemented and nothing was installed into Oblivion. The reset-CALL shim at RVA `0x392B6A6`, persistent generation-tagged per-thread provenance, owner/frame/generation validation, conservative nested fallback and synchronous dispatch-only scopes remain the recommended production design. A successful five-argument trace will validate this diagnostic boundary, not justify returning to evaluation-wide lifetime scopes.

The following is the preserved historical build/review record. Its four-argument source descriptions, old trace hash and live-test instructions are superseded by the confirmation status above; its reverse-engineering evidence and prior implementation history are retained.

---

Latest live result: **Stage 1A direct pass-through reaches the main menu; the minimal C++ trace crashes after its entry marker.** The calling-contract review found a required **fifth stack argument** that both four-argument C++ wrappers omit. The trace's compiled first-entry path passes null in that position. See [CALLING_CONTRACT_REVIEW.md](../reference/calling-contract.md) for the caller evidence, downstream dereference and proposed reset/generation architecture. This latest pass changes documentation only, plus local analysis artifacts; it does not rebuild or install a DLL.

The following records the preceding diagnostic builds. Their direct/trace live outcomes are now known as stated above; the retained scoped/trace source prototypes have not yet been corrected.

**Try `build/MixedInputFix.dll` first.** This is Stage 1A: the original seven-byte entry patch jumps through its nearby slot **directly to the actual PolyHook trampoline**. No C++ evaluation callback, `Evaluation` object, provenance TLS, scopes, logger, extra CALL, return-address substitution or added stack frame executes on this path. The relocated instructions jump to `0x392B637`, and the original function returns directly to its original caller. This removes dependence on the inferred four-argument/void prototype from the hook path.

A pure tail jump never regains control after the original function returns. Adding a return logger would require another wrapper, return-address interception, or debugger instrumentation. Stage 1A therefore logs selection, trampoline verification and successful installation **only**; missing runtime entry/return lines are intentional, not evidence of a crash. The closest minimal diagnostic companion is **`build/MixedInputFix-stage1-trace.dll`**: it uses the same detour/trampoline but a separate C++ function with just a once-only entry marker, a trampoline call, and a once-only normal-return marker. It constructs no evaluation/scopes and does not touch provenance TLS. This companion still assumes `(void*, void*, float, bool) -> void`, changes the call frame/return address, and runs the existing fixed-literal diagnostic I/O. It is not as transparent as Stage 1A.

Reproduce the variants:

```sh
python tools/build_local.py --stage 1 --evaluation-mode direct
python tools/build_local.py --stage 1 --evaluation-mode trace
```

The trace build has a separate DLL/PDB name and does not overwrite the primary direct DLL. The preceding scoped Stage 1 DLL/PDB/build log were saved locally in `build/stage1-wrapper-checkpoint/`. `--evaluation-mode scoped` reproduces the original wrapper selection. `src/DiagnosticStage.hpp` defaults Stage 1 to direct mode; stages 0 and 2–4 default to scoped mode. Direct/trace modes are rejected outside Stage 1.

Interpretation: if the direct build still crashes, the scoped C++ wrapper is not required to trigger the failure. If direct survives and the traced companion crashes after entry, investigate C++ calling assumptions, call-frame effects or diagnostic I/O before blaming evaluation TLS. If the traced companion logs normal return and survives where scoped Stage 1 fails, evaluation/TLS/scope setup becomes the next suspect. Reaching the menu in the pure build alone does not prove this entry ran; use the trace companion to confirm invocation and return. A first-normal-return marker proves at least one normal return, not that every later invocation succeeds.

Focused trampoline audit against the shipping executable:

| Location | Bytes | Effect |
|---|---|---|
| `0x392B630` | `48 8B C4` | `mov rax,rsp`; captures original entry RSP without changing it |
| `0x392B633` | `44 88 48 20` | `mov [rax+0x20],r9b`; writes the fourth home-slot byte |
| `0x392B637` | `48 89 50 10` | Exact continuation: `mov [rax+0x10],rdx`; requires RAX to survive the trampoline jump |

The first two instructions are exactly 3+4 bytes, neither RIP-relative nor branching. Their memory displacement is RAX-based and must not be rebased. Both preserve RFLAGS and RSP. At a standard Windows x64 entry, RSP is 8 modulo 16 and the original return address remains at `[rsp]`. The entry `FF 25 disp32 90` and trampoline `FF 25 disp32` jumps push nothing and clobber no registers. The entry jump's displacement is relative to entry+6; the trampoline continues at entry+7, skipping the padding NOP in patched game memory.

The focused Windows test dumped this actual generated trampoline prefix: `48 8B C4 44 88 48 20 FF 25 4B 00 00 00`. Here the RIP-relative jump at trampoline+7 uses a slot at trampoline+0x58 containing exactly `base+0x392B637`. The slot displacement/allocation address can vary, so preparation now verifies the actual relocated bytes, the indirect-jump encoding, an in-allocation destination slot and its exact continuation target before publication. No replacement trampoline was implemented. PolyHook's bundled `makeTrampoline` still performs the relocation and emits the jump back. No incorrect instruction boundary, register clobber, or continuation was found in this review.

The previous evaluation tests used a RET or a synthetic tail that overwrote RAX after the relocated seven bytes. They did not exercise the real continuation's reliance on RAX. The new `tests/evaluation.cpp` executes the **first 32 shipping bytes**, including both RAX-based argument stores, three pushes and `sub rsp,0x620`, then enters a synthetic body. Direct and unpatched execution matched captured volatile GPR/XMM state, RAX/RSP, original return address, home slots, fifth/sixth stack arguments, RAX/XMM return values and flags; pre-existing provenance TLS stayed untouched. Corrupting the trampoline's continuation slot caused verification to reject it. These are synthetic execution checks, not proof of live startup safety.

Select a cumulative stage with `python tools/build_local.py --stage N`. Without that option, both the local script and normal xmake target use the single default in `src/DiagnosticStage.hpp` (`MIXED_INPUT_FIX_DIAGNOSTIC_STAGE`, currently **1**). Compiler definitions can override it; values outside 0–4 are rejected. Stage 4 retains the production implementation below.

| Stage | Active changes | Patch count |
|---|---|---:|
| 0 | Four proven movement NOPs | 4 |
| 1 | Stage 0 + evaluation entry detour | 5 |
| 2 | Stage 1 + winner hook | 6 |
| 3 | Stage 2 + dispatch hook | 7 |
| 4 | Stage 3 + both provenance-aware camera getter redirects | 9 |

All Stage 1 variants allocate a nearby page with only the evaluation slot populated and prepare the seven-byte PolyHook entry trampoline. **Scoped mode only** enters the existing C++ evaluation wrapper, creates its fresh 128-entry evaluation table, links the TLS evaluation scope, masks any outer dispatch, and calls the relocated original entry once with `(owner, components, float delta, bool paused)`. The scopes restore on normal return and C++/SEH unwind. No winner/dispatch/getter adapters are emitted or installed in any Stage 1 variant; the winner/dispatch slots remain null, no dynamic winner unwind table is registered, and provenance recording/overrides remain disabled. All four movement NOPs stay enabled. Both original camera `cmp al,1` instructions remain byte-for-byte intact at every stage.

Stage 0 prepares no bridge page or evaluation trampoline. Later stages add their prerequisites cumulatively; Stage 2 can collect winners but has no dispatch/getter redirects, and Stage 3 has no getter redirects. All stages retain the complete production signature validation, transactional writes/restoration, and callback lifetime protection. Winner and dispatch remain **six-byte `FF 15 disp32` CALLs**, preserving the `site+6` in-flight-unhook fix. Use a fresh process for each diagnostic DLL.

Diagnostics append to **`<loaded DLL path>.diagnostic.log`** (for example, `main.dll.diagnostic.log` when UE4SS loads a renamed `main.dll`) and also use `OutputDebugStringA`; they are not UE4SS log messages. The file is opened before installing hooks, with append/write-through access, and retained for process lifetime. If opening it fails, debugger output remains available. Each startup has a selected-stage/mode line, followed by verification and successful installation markers. **Direct mode has no runtime markers.** Other modes have first-execution markers in C++ helpers; scoped/trace evaluation also has a first-normal-return marker. Atomic flags prevent per-frame log spam. These paths use fixed literals, preserve Win32 last-error state and do no explicit allocation, formatting or application locking. No logging code was added to assembly bridges. OS I/O still perturbs timing on those first invocations. First-execution messages can precede installation-success messages because the transaction resumes game threads before logging success. A helper marker cannot diagnose a fault in its compiler prologue or an adapter before reaching that helper; absence is not proof the patched entry was never reached.

The evaluation entry has no main-menu/readiness guard. A focused read-only inspection of the shipping prologue confirmed RCX/RDX homing, R9B preservation and XMM2 use in scalar single-precision arithmetic, consistent with the current argument contract. It immediately invokes game routines and checks a nullable virtual-call result; nothing in the inspected entry makes it gameplay-only. Startup can therefore exercise the wrapper with a different owner, empty component collection, zero delta or pause state than the earlier observed live call. The wrapper itself does not dereference owner/components or depend on initialized physical-key globals. It still assumes a normal Windows x64 four-argument call, with the original return behavior; the inspected entry and synthetic tests do not establish every caller's contract. Invalid game objects still fault in original code, and wrapper TLS/stack setup remains a possible crash site. The evaluation table alone occupies about 3 KiB per recursive call, in addition to the game's frame.

New review finding: the old Windows test executed the evaluation trampoline directly, bypassing the actual evaluation wrapper. Tests now cover the installed seven-byte entry detour through that wrapper and trampoline, argument-bit forwarding (including zero, negative zero, infinity and NaN), null/opaque pointers, both bool values, recursive evaluation and C++/SEH scope restoration. Null/opaque pointers reach a synthetic original body; this does **not** imply the real game accepts null objects. The stage tests exercise all five install/restore sets, movement patches, untouched camera comparisons, disabled callback slots and six-byte CALL encodings. The existing in-flight dispatch-unhook regression is retained. No confirmed crash cause was found in this bounded review.

Current validation (2026-09-06): both direct Stage 1A and the trace companion built successfully with five existing UE4SS-header warnings each. The focused evaluation test, host provenance tests and existing Windows standalone suite passed. The focused test's native log contained each trace marker exactly once over repeated calls; the direct path entered no C++ evaluation helper. All 15 shipping-image signatures matched; both DLLs export `start_mod` and `uninstall_mod` as Windows x64 images. Wine used `/tmp/mixed-input-fix-wine` and synthetic test memory. No live-game files were written. Focused test commands: `python tools/build_local.py --evaluation-tests`, then `WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/evaluation-tests.exe`.

Primary artifact: `build/MixedInputFix.dll`; PDB: `build/MixedInputFix.pdb`; build log: `build/build.log`. Direct DLL SHA-256: `f8aac2c35fbc90f982be8c7e657983b6982755039ce61eea79b047cbbc4729e6`. Trace companion: `build/MixedInputFix-stage1-trace.dll` with matching PDB and `build/stage1-trace-build.log`; SHA-256: `cfe2b1620c9c311ab8e15d433fea07566c1c40dbc40f25a2f1d632fc465bf102`. Test results: `build/evaluation-tests.log`, `build/bridge-tests.log`; shipping entry inspection: `build/evaluation-entry-review.txt`.

Files changed for this diagnostic pass: `src/DiagnosticStage.hpp`, `src/dllmain.cpp`, `tools/build_local.py`, `tests/evaluation.cpp` (new), and `README.md`. Production provenance rules, existing standalone test sources and the signature manifest were left intact.

The following describes the preserved **Stage 4 production implementation** and its prior validation; the current DLL enables only the Stage 1 subset above.

The four movement NOPs are retained. Camera routing now follows the physical mapping that won the game's existing max-magnitude merge. The original camera comparisons and branches remain unchanged. This preserves the game's merge policy; it does not sum mouse and stick input or invoke a camera handler twice.

The implementation uses two linked thread-local scopes. Evaluation entry creates a fresh, allocation-free table, including for recursive evaluations of the same owner. Dispatch snapshots a winner only when evaluation owner, action object, and action-instance identity match. Every dispatch pushes a context, including Unknown, so a nested unrelated event masks an outer event. Scope cleanup runs on normal return, C++ exceptions, and Windows structured exceptions (`/EHa`). No process-global last-source variable is used.

At a winning store, the bridge reads owner R14, instance RDI, component RCX, caller `[RBP+0x3F]`, action `[RBP+0x4F]`, and physical FKey pointer `[RBP+0x1F]`. Only caller RVA `0x392BCBF` can produce a known source. Foreign callers and unknown keys replace earlier provenance with Unknown. Losing mappings bypass the bridge; ties reach it and replace earlier winners. Broken record reads or the 128-action table limit disable the evaluation's overrides.

Only Axis1D instances (`instance+0x50 == 1`) with max policy (`action+0x51 == 0`) qualify. The policy and identity are checked again at dispatch and getter time. Additive policy, other value types, mismatched axes, missing evaluations, and unknown sources use the original getter.

All addresses below are RVAs added to `GetModuleHandleW(nullptr)`.

| Site | RVA | Installed strategy |
|---|---:|---|
| Evaluation entry | `0x392B630` | Seven bytes: `FF 25 disp32 90`, using a nearby pointer slot to the scoped C++ wrapper. PolyHook decodes and relocates the original two instructions into its trampoline. |
| Mapping winner | `0x3934891` | Six bytes: `FF 15 disp32`, an indirect CALL through a nearby pointer slot. AsmJit bridge saves RFLAGS, RAX/RCX/RDX/R8–R11 and XMM0–5, calls the recorder, restores registers, replays `movsd [rbp+rcx*8-0x69],xmm2` once, and returns directly to `0x3934897`. XMM6–15 and other nonvolatile registers are preserved by the Windows ABI. |
| Event dispatch | `0x392CD15` | Six bytes: `FF 15 disp32`, replacing `mov rax,[rcx]; call [rax+8]` (original CALL at `0x392CD18`). A leaf adapter passes binding RCX, instance RDX, owner R13, and the original vtable target to a scoped C++ wrapper. It executes that target once and resumes at `0x392CD1B`. |
| Horizontal getter CALL | `0x489D2F9` | Five-byte CALL to a near leaf adapter and provenance helper. |
| Vertical getter CALL | `0x488A0E9` | Five-byte CALL to a near leaf adapter and provenance helper. |
| Original getter | `0x2E6CC30` | Unmodified. Called on fallback, returning its original result. |
| Native horizontal handler | `0x489D210` | Reference only; no entry detour. |
| Native vertical handler | `0x488A000` | Reference only; no entry detour. |
| Backward movement | `0x488AC43` | `75 0F` → `90 90` |
| Forward movement | `0x488AD39` | `75 0F` → `90 90` |
| Left movement | `0x488AE33` | `75 0F` → `90 90` |
| Right movement | `0x488AF29` | `75 0F` → `90 90` |

The getter helpers return 0 for a Mouse winner and 1 for a Gamepad winner. The old writes to comparison immediates at `0x489D2FF` and `0x488A0EF` have been removed. Both sites must contain their original immediate 1.

| Physical FKey global | RVA |
|---|---:|
| MouseX | `0x91132C0` |
| MouseY | `0x91132D8` |
| Gamepad_RightX | `0x9113F20` |
| Gamepad_RightY | `0x9113F38` |

The full eight-byte shipping FName identity is read from each global at runtime. Unreadable, zero, or duplicate global identities produce Unknown. No observed runtime FName IDs or heap addresses are hardcoded.

AsmJit emits a page of nearby adapters, finalized as executable/read-only. The non-leaf winner bridge has registered Windows unwind metadata, including separate stack descriptions at POPFQ and RET. Dispatch and getter adapters are leaf tail jumps; their C++ wrappers provide compiler-generated unwind metadata. PolyHook's local `makex64MinimumJump` API returns `{destination slot, jump}`; the implementation explicitly selects the six-byte jump and supplies its own nearby slot rather than relying on automatic detour sizing or VirtualAlloc2 allocation. It uses the bundled protected decoder/relocator APIs, so a future PolyHook upgrade requires review.

Installation validates the PE type and every signature before preparing code. It rechecks the complete signature set after suspending the other enumerated process threads, before changing any bytes. Instruction pointers inside a patch range abort the transaction. All required pages must become writable before any of the nine patches are written; cache-flush failure rolls back the bytes. Page protections are restored in reverse order. AsmJit, PolyHook, allocation, and logging are kept outside the suspended interval. A rare protection-restoration refusal is reported while retaining valid callback storage.

On UE4SS uninstall, provenance is disabled and original bytes are restored if the installed bytes still match. The DLL is pinned and its published trampoline/bridge storage is retained until process exit to protect callbacks already in flight. Both six-byte CALLs push the original `site+6` continuation, so restoring original bytes cannot strand an in-flight return inside an instruction. Reload requires a fresh process. Existing patches from the old DLL or another mod fail validation; this implementation does not overwrite them.

Use the normal UE4SS startup lifecycle. This is not a general concurrent hot-patching API: thread enumeration cannot prevent arbitrary new threads from being created during a transaction.

The exact signature manifest follows. `tools/validate_image.py` matched all 15 against the local shipping executable. Executable SHA-256:

`b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`

| Validation | RVA | Expected original bytes |
|---|---:|---|
| evaluation entry | `0x392B630` | `48 8B C4 44 88 48 20 48 89 50 10 48 89 48 08 55 53 57 48 8D A8 C8 FA FF FF 48 81 EC 20 06 00 00` |
| evaluation reset | `0x392B69E` | `44 0F 28 F2 48 89 4D 90 E8 F5 E8 00 00` |
| physical mapping caller | `0x392BCBA` | `E8 91 88 00 00 EB 0E` |
| mapping frame and instance | `0x3934550` | `48 8B C4 48 89 50 10 55 57 41 54 48 8D 68 C1 48 81 EC F0 00 00 00 48 89 58 08 48 8B DA 4C 89 70 E0 4C 8B F1 4C 89 78 D8 44 0F 29 48 98 44 0F 28 CA E8 AA 9D FF FF 48 8B F8` |
| action policy field | `0x39347CC` | `48 8B 07 41 39 4F 08 44 88 54 24 30 41 0F 9F C4 44 0F B6 40 51` |
| additive bypass | `0x3934858` | `45 85 C0 74 19 44 3B C2 75 14 F2 0F 10 44 CD B7 F2 0F 58 44 CD 97 F2 0F 11 44 CD 97 EB 21` |
| winner and tie branch | `0x3934876` | `F2 0F 10 54 CD B7 F2 0F 10 44 CD 97 0F 28 CA 0F 54 CB 0F 54 C3 66 0F 2F C8 72 06 F2 0F 11 54 CD 97 48 FF C1 49 3B C9 7C B9` |
| dispatch contract | `0x392CD0F` | `49 8B 0E 48 8B D7 48 8B 01 FF 50 08 49 8D BD A8 05 00 00` |
| original CommonInput getter | `0x2E6CC30` | `0F B6 81 91 00 00 00 C3` |
| horizontal getter and branch | `0x489D2F9` | `E8 32 F9 5C FE 3C 01 0F 85 02 06 00 00` |
| vertical getter and branch | `0x488A0E9` | `E8 42 2B 5E FE 3C 01 0F 85 02 06 00 00` |
| backward movement | `0x488AC41` | `3C 01 75 0F 0F 57 C0` |
| forward movement | `0x488AD37` | `3C 01 75 0F 0F 57 C0` |
| left movement | `0x488AE31` | `3C 01 75 0F 0F 57 C0` |
| right movement | `0x488AF27` | `3C 01 75 0F 0F 57 C0` |

Build completed with Clang-cl / LLD 22.1.8, the installed MSVC 14.51.36231 headers/runtime libraries and Windows SDK 10.0.26100.0. It links the existing UE4SS import library and bundled static PolyHook 2, AsmJit, AsmTK, Zydis, and Zycore libraries. There were no errors and five warnings from existing UE4SS headers. The DLL is Windows x64 and exports `start_mod` and `uninstall_mod`.

Output: `build/MixedInputFix.dll` (absolute path `build/MixedInputFix.dll`). PDB: `build/MixedInputFix.pdb`. Build log: `build/build.log`.

Reproduce this local build with `python tools/build_local.py`. The script uses the already configured UE4SS target's include/define metadata and writes all outputs inside this mod. `tools/clang_compat.hpp` supplies a matching forward declaration needed by an existing UE4SS template that Clang otherwise rejects. The normal `xmake.lua` target was also updated for static AsmJit and `/EHa`; this build used the local script, not the parent xmake build.

Validation completed:

- Host C++ tests passed: replacement, Unknown, instance identity, axis filtering, nested owners, exception restoration, thread isolation, and capacity fallback.
- Standalone Windows tests passed in an isolated Wine prefix: actual winner/dispatch bridges, displaced store, volatile register and carry-flag preservation, body/epilogue unwind metadata, single binding execution, original-getter fallback, additive rejection, C++/SEH dispatch cleanup, PolyHook staging and trampoline execution, late byte-mismatch rejection, all nine patches installed/restored on synthetic memory, and unhooking from inside an active dispatch callback before it returns.
- All 15 production signatures matched the local executable through read-only PE inspection. Export inspection and Python syntax checks passed.

Test commands: `c++ -std=c++20 -Wall -Wextra -Werror -pthread tests/provenance.cpp -o build/provenance-tests`, `build/provenance-tests`, `python tools/build_local.py --bridge-tests`, then `WINEPREFIX=/tmp/mixed-input-fix-wine WINEDEBUG=-all wine build/bridge-tests.exe`. Supply the shipping executable path to `python tools/validate_image.py` for the read-only signature check.

Remaining uncertainty includes the reported delayed startup crash of the full live build and live gameplay behavior. The user supplied live proof for horizontal winner provenance and synchronous dispatch; vertical MouseY/RightY and the LookUpInput synchronous chain still need live confirmation. The current Stage 1 diagnostic DLL has not been loaded into the game. Controller-only, mouse/gyro-only, simultaneous input, menus, save transitions, and reconnect/focus behavior remain untested. The implementation intentionally falls back for additive and multidimensional actions and preserves the game's existing winner selection.

Changed source/support files: `src/dllmain.cpp`, `src/Provenance.hpp`, `src/Sites.hpp`, `xmake.lua`, `tests/provenance.cpp`, `tests/bridges.cpp`, `tools/build_local.py`, `tools/clang_compat.hpp`, `tools/validate_image.py`, `.gitignore`, and this `README.md`. Existing changes elsewhere in the UE4SS tree were left intact.

Review correction retained: the original five-byte CALL plus NOP at the winner and dispatch sites pushed `site+5`. Restoring original bytes during an in-flight callback could therefore return into the final byte of an original instruction. These two sites use six-byte indirect CALLs (`FF 15 disp32`) through bridge-page slots at offsets `0xA08` and `0xA10`. The getter CALLs remain five bytes because that matches their original instruction length. A regression test restores the original dispatch sequence inside the active binding, then verifies one callback, correct return, and TLS restoration.

Runtime review limits: the evaluation wrapper assumes the four-argument Windows x64 signature `void(owner, components, float, bool)`. The winner bridge assumes the verified mapping frame and 16-byte caller stack alignment; its replayed store is intentionally unguarded, as in the original game. Dispatch dereferences the binding vtable and calls its two-argument target without suppressing game faults. The fallback getter reads `object+0x91` and can fault on a stale object even though provenance metadata reads are guarded. Dynamic unwind tests do not establish behavior under every game/runtime mitigation or arbitrary stack manipulation. A new thread missed by the suspension snapshot can encounter a partially written patch; failed thread resumption can leave a thread paused. These constraints prevent treating the standalone results as proof of live-game crash safety.
