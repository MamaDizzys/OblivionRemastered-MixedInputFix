Camera accumulator investigation, 2026-09-08. Production, provenance, and movement are unchanged. This observer requires no DLL build or installation.

**2026-09-11 live update:** Both new captures completed with zero errors at `event_limit`. Opposition felt like continuous tugging; the hard axis seizure did **not** reproduce. These are healthy comparisons. The heavier probe may alter timing. Do not require repeated heavy-probe reproduction: proceed to the [single-checkpoint camera view observer](camera-view-capture.md), using the preserved visible-stall capture as the reason to advance beyond control yaw.

Raw traces are preserved under `build/camera/accumulator/live-2026-09-11/`, with source paths, hashes and symptom classification in `provenance.json`. `analyze_camera_accumulator.py` now emits identity/stack/order-checked `consumer_sequences` and contiguous `intervening_cycles` in its summary JSON.

| Check | `01-X-mouse` | `02-X-opposecontinue` |
|---|---:|---:|
| Native adds / changed native-add writes | 218 / 218 | 222 / 222 |
| Native callers: mouse / gamepad handler | 218 / 0 | 218 / 4 |
| Complete consume → manager before/after → setter entry/return | 224 | 222 |
| Local delta equals accumulator; initial view equals control | 224 / 224 | 222 / 222 |
| Manager leaves local delta zero; request equals manager view | 224 / 224 | 222 / 222 |
| Returned full rotation exactly equals request | 222 / 224 | 222 / 222 |
| Changed tick-tail clears | 217 | 222 |
| Complete contiguous add-through-clear cycles | 217 | 222 |
| Errors | 0 | 0 |

In **all 222 opposing cycles**, the exact order is `add → native_add write → history_copy → consume → manager_before → manager_after → set_enter → set_return → tick_tail_clear`. History, consumed yaw and pre-clear yaw equal the written accumulator. The manager adds the yaw delta to view yaw (wrapped to 0..360) exactly, zeros the local delta, and the normal consumer's setter request is committed exactly before the clear. Every setter caller is RVA `0x359b4e6`; the live manager processing target is RVA `0x48905e0`. There are no `sign_test`, `sign_skip` or `sign_submit` events. Their absence here does not rule them out during a hard stall.

The four gamepad-handler adds are near the sample's end at seq 1937, 1955, 1964 and 1973, each in its own add-through-clear cycle. Caller counts do not establish simultaneous within-cycle cancellation, physical device provenance, or the arbitration winner. The `continue` suffix is an accidental label; the capture is complete. Sampling spans about 1.84 seconds of debugger host time before the row limit, not the nominal three seconds or a measured game-time interval.

The mouse baseline has seven zero-yaw consumer calls and a partial final interval. Three manager-after yaws differ from exact yaw addition by float-sized rounding (before seq 283, 289 and 1993). Two corresponding setter requests (seq 285 and 1995) leave full control rotation unchanged; yaw differences are about 0.00000456° and 0.00000378°. These exceptions are retained, not reported as hard stalls or universal exact transfer. Static setter checks precede its store; attributing these individual exceptions to a branch would need another checkpoint and is unnecessary for advancing. The baseline sample spans about 1.87 seconds of debugger host time.

The preserved `06-X-oppose` receiver snapshots establish a stronger boundary than handler output alone: **92 paired X calls changed the actual double at `+0x530` from zero to nonzero; all 91 successive sampled control-yaw changes exactly matched the preceding accumulator value.** The user visibly reproduced the stall during this capture. Controller yaw is not necessarily the final camera pose. Equality at successive checkpoints does not exclude intervening writes or precisely time the visible symptom.

The reproducible extraction is `build/camera/accumulator/06-preserved-checkpoints.json` and `.csv`. It decodes actual before/after bytes, not sums of handler outputs. For example, output seq 44 / after seq 45 has `+0x530: 0 → 0.28119003772735596`; the next X checkpoint's controller yaw advances by exactly that amount. The handler scalar was `0.11247601360082626`, before receiver scaling. These stages must not be treated as having identical scales.

Static findings use shipping SHA-256 `b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`. Addresses below are preferred image VAs (`base=0x140000000`); the observer relocates RVAs from the validated live base.

| Site | Established operation |
|---|---|
| `0x143564e96`, store `0x143564e9e` | Add converted, receiver-scaled X contribution to double `receiver+0x530`, then store it. Any caller of this target reaches this store, including callers outside the two X handler sites. |
| `0x143589e2d` | Zero vector store across `+0x528..+0x537`, clearing pitch and yaw, conditional on `vtable+0x838`. Followed by clearing `+0x538`. Called from game consumer `0x14488edd0`. This is a clear site, not the established stall explanation. |
| `0x143596a8f` | Same zero-vector clear on an early path in the controller tick routine beginning `0x1435969e0`. |
| `0x1435970b0` | Same zero-vector clear on the tick tail. Constant `0x148daa060` is verified zero. |
| `0x14359b34b` | Read `+0x528..+0x537`; copy pitch/yaw to local delta at current `rsp+0x48`. Roll comes from `+0x538`. |
| `0x14359b39b` | Pass local delta (`r9=rsp+0x48`) and view rotation (`r8=rsp+0x30`) to `receiver[+0x350]`'s `vtable+0x868`. The manager can modify both. |
| `0x14359b3a1` | After that call, or the null-manager path. Observe resulting local delta/view rotation. Later code can also adjust view rotation before submission. |
| `0x14359b4e0` | Submit view rotation through controller `vtable+0x768`. |
| `0x143114967`, `0x1431149cd` | An alternate `+0xc00` consumer (`0x143114840`, vtable `0x14762d050`) reads yaw for a zero/modulo check and adds it to local rotation. The narrow live probe requires the normal `+0xc00` target above; it rejects this alternate layout instead of silently missing its consumer. |
| `0x1430bace0` | Controller `vtable+0x760` accessor copies doubles at `+0x310/+0x318/+0x320`. The middle double, `+0x318`, is the control-yaw checkpoint. |
| `0x1430d1c90` | Controller `vtable+0x768` setter. Validity/magnitude/difference checks precede store `0x1430d1e61` to `+0x310..+0x31f`. Return checkpoint `0x1430d1ed7` retains receiver in RBX; entry stack is current `rsp+0xb8`. |
| `0x14488fb10..0x14488fb32` | Additional consumer within `0x14488edd0` compares computed yaw delta in XMM3 with zero and accumulator `+0x530`. For finite values, opposite nonzero signs take `0x14488fb34`. The computed delta is not an Enhanced Input winner observation. |
| `0x14488fb34` / `0x14488fb75` | The first clears state at `+0x928`, `+0x930`, `+0x938..+0x954` and skips this path's controller setter; the second submits a proposed rotation. Neither writes `+0x530`. Live involvement in the stall remains unverified. |
| `0x14488fb9b`, copy `0x14488fbf6` | Read accumulator vector and copy it to history at `+0x9a0` (yaw `+0x9a8`), then roll to `+0x9b0`. This is a read/history copy, not an accumulator clear. |

On-disk vtable `0x147bde600` ties together output slot `+0xd18 → 0x143564e20`, additional consumer `+0xbe0 → 0x14488edd0`, and normal consumer `+0xc00 → 0x14359b340`. Vtable `0x147c35c30` uses wrapper `0x14488fc80`, which calls `0x14488edd0` at `0x14488fcb0`. This is static linkage, not proof of the current live receiver's vtable. The probe selects a fresh receiver at the native X add, verifies output/getter/setter/normal-consumer slots, and records the live additional-consumer target. The static output includes all four references to the native X output function in `vtable-links.json`.

The whole `.text` scan includes direct `+0x530` accesses, overlapping vector accesses and address-taking candidates. A matching displacement alone does not identify an object: `0x1435bc25e` writes the same offset in a layout with a flag at `+0x534`; `0x144885b62` takes `+0x528` from a `0x7b0`-stride table entry. These are not attributed to the camera receiver. Static scanning cannot prove absence of aliased, indexed, bulk or external-module writes. One live hardware watchpoint covers **changed writes to the selected eight bytes**, regardless of writer instruction/module. No independent opposing accumulator writer has yet been established.

Reproduce static validation and extraction from the repository root:

```sh
python tools/camera_accumulator_static.py '/path/to/SteamLibrary/steamapps/common/Oblivion Remastered/OblivionRemastered/Binaries/Win64/OblivionRemastered-Win64-Shipping.exe' --scan
python tools/analyze_camera_accumulator.py build/camera/live-2026-09-08/mif-camera-06-X-oppose-1788920943162121092.jsonl --legacy-output build/camera/accumulator/06-preserved-checkpoints
python tests/camera_accumulator.py --gdb
```

Disassemblies and scan candidates are under `build/camera/accumulator/static/`. Extraction leaves the original raw capture intact. The GDB test uses a disposable native fixture, including a newly created thread, without attaching to the game.

For direct live consumer timing, use a **fresh GDB session**, the same production candidate and input settings as trial 06. Stand still, on foot, away from camera-mode transitions. One healthy mouse-X comparison followed by opposing X is sufficient; repeating all six upstream baselines is unnecessary.

```sh
pgrep -af '[O]blivionRemastered-Win64-Shipping\.exe'
gdb -q -nx
```

Substitute the actual PID:

```gdb
set pagination off
set print thread-events off
set debuginfod enabled off
set auto-solib-add off
handle SIGUSR1 nostop noprint pass
attach PID
source tools/camera_accumulator_capture.py
mif-camera-base
mif-accumulator-find
continue
```

Move X briefly. GDB stops at the next native X add and prints the selected receiver. Release controls. Discovery avoids reusing a stale address from the earlier capture. If attach is denied, use `sudo gdb -q -nx` as in the original guide. Do not run the broad camera/movement observers or another watchpoint capture concurrently. The imported camera module registers its commands for shared candidate validation but installs no broad probes.

```gdb
mif-accumulator-trial 01-X-mouse
continue
```

Focus the game and perform continuous mouse-X motion. Timing begins on the first running add to the selected receiver: **8 seconds preparation, then 3 seconds sampling**. Only the add probe runs during preparation. Sampling uses **10 software sites and one eight-byte hardware write watchpoint**, filtered to that receiver. The sites cover only the accumulator and two immediate consumer paths, including the shared controller setter. There are no mapping, provenance, movement, Y-handler or response-state probes.

Capture stops after the sample at the next observed changed clear, at 2000 rows, or on a probe after a further 2-second grace period. Limits depend on probes executing. If still running after about 15 seconds, press Ctrl+C and stop manually. If hardware-watchpoint insertion fails, stop and preserve the error; the tool rejects software-watchpoint fallback. Debugger probes perturb timing.

```gdb
mif-accumulator-stop
mif-accumulator-report
mif-accumulator-trial 02-X-oppose
continue
```

Use the opposing-X pattern that reproduced trial 06, then stop/report again. Note whether the visible stall occurred and any hand-repositioning interval. Preserve the unique `/tmp/mif-accumulator-LABEL-TIMESTAMP.jsonl`, `.summary.json`, and `.events.csv` paths. Raw rows include double values/bits, thread, receiver, PC, caller, consumer/setter IDs, local deltas and controller yaw. Rerun discovery after changing scene/controller or restarting the game.

Interpret the sequence in this order:

1. Match `add` to changed `write` by `add_id`, thread/stack and receiver. `contribution` is the double immediately before native `addsd`; watchpoint `before/after` are actual memory values. `caller_kind` identifies native call sites only. `other_caller` establishes a caller outside the two known X output probes, not a device/source classification.
2. Inspect all changed `write` rows. Known zero-vector clears are named; unknown writes retain their **post-write PC**, registers and a bounded backtrace when available. Disassemble an unknown writer before adding sites.
3. Follow `consume → manager_before → manager_after` by `consumer_id`. Check the local yaw delta against the actual accumulator and the manager's effect on view yaw. An after row without a before row can mean the null-manager path or an initially partial interval.
4. Compare `set_enter.requested_rotation` with paired `set_return.control_rotation`. All calls to the validated setter for this receiver are observed, including other callers. Follow actual order around clears; do not assume one consumption per Enhanced Input generation.
5. Check `sign_test → sign_skip/sign_submit` by `sign_id`. Neither perceived direction nor arithmetic trace sums prove that this path caused a stall. `history_copy` records the copied delta and preceding history.
6. If accumulator, consumed delta and control yaw track normally, the next boundary is the camera pose/view consumer of control rotation, **outside this probe**. The preserved 06 checkpoints already support advancing to that boundary; this trace can establish the exact intervening calls if needed.

GDB reports a write watchpoint only when watched bytes change. Zero-to-zero clears and identical-bit stores are omitted; absence does not mean the store failed to execute. Initial/final intervals may be partial, and a nonzero add can round to an unchanged accumulator. The observer never calls inferior functions or edits input values, registers, accumulation or rotation. It removes only its own breakpoints/watchpoint.

```gdb
mif-accumulator-stop
detach
quit
```
