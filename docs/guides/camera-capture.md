**Next boundary: returned camera view (2026-09-11).** The preserved opposing-X stall retained healthy Mouse/X provenance and accumulator → successive control-yaw transfer. The new [accumulator captures](camera-accumulator-capture.md) establish the exact intervening sequence during healthy opposition (continuous tugging, no hard seizure). Proceed to the [single-checkpoint camera view observer](camera-view-capture.md); repeated heavy-probe stall reproduction is not required. The six-trial instructions below are retained as capture history.

**View follow-up also completed healthy:** Use the [downstream map and detached pose polling](camera-pose-poll.md) next. Both view captures validate the copy/control path without reproducing the hard stall. The shared getter still caused many GDB stops; no additional GDB trial is required.

**Camera investigation active (2026-09-08).** The hours-long shutdown diagnostic menu-exit trial and subsequent production Alt+F4 trial both exited cleanly. The [preserved shutdown baseline](shutdown-diagnostic.md#clean-live-baseline--2026-09-08) leaves the earlier failure intermittent and no longer blocks camera capture. Use the restored production candidate below; preserve the shutdown tooling for another naturally occurring failure.

Camera conflict observation, 2026-09-07. Movement is **Live Verified**. Keep the current production candidate, `build/MixedInputFix-production-candidate.dll`, SHA-256 `7551c3af9193e2556af7671fbac9b6f0458753f8271430db1fac7e182a21830c`. No DLL rebuild, installation, production patch, priority change or movement retest is needed. The updated observer requires this candidate’s helper bytes and the original camera `cmp al,1` / movement branches.

The objective is to locate the first loss of motion: mapping winner → action modifiers → dispatch/handler → chosen camera path and retained state → processed output → downstream receiver. A brief zero result from balanced opposing inputs is not sufficient evidence of a bug. Compare unequal inputs and recovery when one source releases. Mouse deltas and stick rates have different units/scaling; their raw magnitudes are not comparable as angular motion.

Start with six short captures, one file per trial. Keep both axes instrumented in every trial, including X-only input. Do not run the movement observer concurrently. Use a fresh GDB session if an older camera script has already been sourced. The raw JSONL is the evidence; the report is a bounded convenience view.

Before attaching, reproduce the opposing-X symptom once without GDB. Note whether it occurs using a physical mouse, Steam Input gyro, or both; the observer sees engine MouseX/Y and cannot distinguish their physical origin. Keep the same Steam Input layout, sensitivity, acceleration/deadzone, inversion, gyro gating and mods throughout the comparison. Ensure right stick is native gamepad input and gyro is true mouse output. Record these settings briefly; do not change them speculatively. Stand still on foot in an open area, away from interaction/camera-mode transitions. Keep Y away from pitch limits. Avoid left-stick or keyboard movement input during captures.

Find and attach to the shipping game process in a terminal:

```sh
pgrep -af '[O]blivionRemastered-Win64-Shipping\.exe'
gdb -q -nx
```

At GDB, substitute the actual shipping process PID:

```gdb
set pagination off
set print thread-events off
set debuginfod enabled off
set auto-solib-add off
handle SIGUSR1 nostop noprint pass
attach PID
source tools/camera_capture.py
mif-camera-base
```

Expect `Validated camera candidate helper/probe bytes; $mif_base = ...`. The command checks the live reset/dispatch/getter patch structure, exact DLL helper bytes, game probe bytes, and original movement branches. It does not hash the entire loaded DLL. The shipping image used for static validation hashes to `b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`. Do not guess the loaded base from the usual `0x140000000`. If validation fails, keep the game stopped and return the error plus `info proc mappings`; do not weaken the signatures. If attach reports `ptrace: Operation not permitted`, quit the unattached GDB and repeat with `sudo gdb -q -nx`; no system-wide ptrace change is necessary.

For the first trial:

```gdb
mif-camera-trial 01-X-stick
continue
```

Immediately focus the game and perform the input below. Timing begins on the first running reset probe: **8 seconds preparation**, then **3 seconds contiguous recording**. Hold or repeat the trial input through the whole interval until the game freezes automatically. Only two reset-related probes run during preparation. Recording stops at the first reset after the 3-second interval, or at **6000 recorded rows**; a 2-second grace interval permits a partial-window timeout on a later probe. All these limits depend on probes executing. If the game has not stopped after about 15 seconds, return to GDB, press Ctrl+C, and stop manually. Do not treat GDB-induced slowness as the gameplay stall.

After the automatic stop, release controls and return to GDB:

```gdb
mif-camera-stop
mif-camera-report
```

Stop is harmless if capture already closed. The report writes full `.summary.json` and `.summary.outputs.csv` companions and prints at most 150 lines. Preserve the unique `/tmp/mif-camera-LABEL-TIMESTAMP.jsonl` path printed when arming; do not overwrite or edit it. A useful capture has no `capture_error`, at least one complete identified reset-to-reset window, and the expected camera handler calls. An event-limit capture can still contain useful complete windows; its final window is partial. A truncated console report is not a truncated raw file. If it stops before any complete window, return that file before increasing the limit or adding probes.

Repeat the same three-command cycle (`mif-camera-trial LABEL`, `continue`, then stop/report after freezing) for this table. Direction labels mean resulting camera direction, taking inversion into account.

| Order / label | Input throughout preparation and sample | Purpose |
|---|---|---|
| `01-X-stick` | Native right stick held about one-third to one-half right, Y centered; mouse stationary/gyro still | Stick-X branch, response state and output baseline |
| `02-X-mouse` | Right stick centered; continuous mouse/gyro sweep right, Y as still as practical | Mouse-X source, modifier, branch and output baseline |
| `03-Y-stick` | Native right stick held moderately up, X centered; mouse/gyro still | Confirm the live vertical chain independently; stay away from pitch clamp |
| `04-Y-mouse` | Right stick centered; continuous mouse/gyro sweep up, X as still as practical | Mouse-Y chain and output baseline |
| `05-X-same` | Same moderate right stick as trial 01 plus rightward mouse/gyro sweep like trial 02 | Same-direction simultaneous control, dispatch multiplicity and shared state |
| `06-X-oppose` | Same moderate right stick, but continuous leftward mouse/gyro sweep; vary sweep speed slowly from weak correction to clearly stronger correction and back | Reproduce opposition while passing through different magnitude relations and source transitions |

Use gyro’s available sweep range or a long physical-mouse sweep; if you must recenter, note that interval. Repeated sweeps are acceptable, but their return strokes produce same-direction input in trial 06, so say that explicitly. Keep gyro still for stick-only trials without changing its layout/gating settings. If a Y-only trial reaches the pitch limit, discard that trial for stall analysis and repeat from mid-pitch at lower deflection. The observer records incidental cross-axis input so a nominal X-only trial is not assumed perfectly isolated.

Check the first report before continuing: no read/layout errors and actual expected input/output rows. Once all six are captured, return their reports and raw files, plus which trial reproduced the ordinary-gameplay symptom. Do not change production based solely on a visually stationary camera under GDB. No normal-frame-duration claim can be made from this trace.

Follow-up trials are conditional, after locating the suspicious stage in those files:

| Label | Input | When useful |
|---|---|---|
| `07-X-release-mouse` | Keep moderate right stick held. Repeatedly sweep mouse/gyro against it for roughly one second, then keep mouse/gyro still for roughly one second; repeat through preparation and capture | Does healthy stick output recover immediately when MouseX becomes zero, or retain suppressed response/history? |
| `08-X-release-stick` | Keep leftward mouse/gyro motion going. Repeatedly hold moderate opposing right stick for roughly one second then center for roughly one second | Reverse release order; isolate retained state after stick relinquishes ownership |
| `09-X-reversed` | Native **right stick pushed moderately left** plus rightward mouse/gyro sweep | Only if a sign-specific asymmetry remains; distinguish sign from source |
| `10-Y-oppose` | Moderate native right stick up, downward mouse/gyro sweep, X neutral; stay mid-pitch | Verify whether Y has the same mechanism once X is understood |
| `11-X-conflict-Y-control` | Reproduce opposing X while adding a small, unopposed Y camera input | Check the user’s responsive-other-axis observation against the gamepad path’s shared X/Y reads |

These are input patterns, not precise timing claims. Use the actual trace values and clears to locate transitions. Do not ask the user to hit an exact floating-point tie. If contiguous GDB capture prevents reproduction or misses the transition, retain the healthy baseline and stop expanding probes; a separately reviewed, fixed-size in-process observer buffer may be the next step. That would be a new diagnostic artifact and is not implemented or required by this first pass.

Read the evidence in this order:

1. Use complete thread/generation/owner/frame windows. Follow each camera action/instance from all mapping candidates, policy and `merge_before/after` to the recorded winner. For policy 0, a losing opposite mapping does not imply a zero merged value. Different actions or bindings may take different paths. Check across consecutive windows for sign/source alternation as well as within one window.
2. Compare `action_before/after`, dispatch value and handler input. A change to near zero here localizes the issue before the camera branch. Modifier addresses/counts are recorded; inspect only the active modifier chain next if needed. Winner provenance intentionally survives action modifiers.
3. Match each handler’s dispatch ID, winner record and active snapshot to actual getter AL, expected axis, type/policy and generation. `common_type` is sampled from the CommonInput object saved before its getter CALL; post-helper RCX is volatile. Unknown/fallback and a mismatched snapshot must remain visible. A missing getter probe can be the native null-subsystem or alternate-mode path; it is not automatically a capture failure.
4. Compare handler input, entry/branch/output/return `latest_x`, `latest_y`, `gain_x`, `gain_y`, and final output. An entry plus native RET with no output is distinct from a partial capture. A nonzero input with suppressed output localizes loss to the handler but does not prove that the four visible fields alone caused it. Use the isolated/same-direction baselines to decide whether to instrument response scaling or the alternate-mode path more narrowly.
5. Count actual outputs by receiver and axis. Two equal/opposite processed outputs, or alternating signs over consecutive evaluations, can explain little visible net motion, but **the report’s arithmetic sum is not proof of engine accumulation or a defect**. Every output records its actual RCX receiver, virtual target, first 128 target bytes and before/after receiver bytes at `+0x300..+0xD6B`; the summary lists changed four-byte words. Empty differences in this bounded range do not exclude state elsewhere or behind a pointer.

If motion is lost downstream, use the `output_target` from that live trace. With GDB stopped and `mif-camera-stop` completed, inspect the exact address printed in the JSON/CSV (substitute `0xACTUAL_TARGET`):

```gdb
x/32i 0xACTUAL_TARGET
```

Return that disassembly with the paired output/after rows. Resolve any jump/thunk and identify the actual store, target object and later consumer before selecting further probe addresses. The next bounded trace should record that store before/after and the consumer’s read/reset for the same receiver and axis; do not install a broad watchpoint set or call engine functions from GDB. Addresses/field semantics for that follow-up cannot be specified honestly until the live virtual target is known. Consumer windows may span several input evaluations; generation-local sums alone are insufficient.

If observation shows that independently processed stick and mouse angular contributions can safely share that accumulator, composition at that stage is a candidate for a later fix. If a single max-merged action has already discarded one contribution, two contributions cannot be reconstructed from its final scalar and winner tag; any later fix would need source contributions retained earlier and processed in their appropriate units. Neither case justifies global source priority, forcing the mouse path, summing raw mouse/stick values, clearing shared state speculatively or switching action policy to additive now.

Tool changes and validation are recorded in the [movement and camera reference](../reference/movement-and-camera.md). Offline checks:

```sh
python tests/camera_capture.py
python tests/movement_capture.py
python tools/analyze_camera_capture.py /tmp/mif-camera-LABEL-TIMESTAMP.jsonl
```

To finish the live session, with the inferior stopped:

```gdb
mif-camera-stop
detach
quit
```

The observer removes only its own software breakpoints. It never calls inferior functions or edits game input values/registers. Software breakpoints temporarily replace instruction bytes in the normal debugger manner; timing is perturbed throughout. Production source and the candidate DLL remain untouched.
