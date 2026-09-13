Camera view investigation, 2026-09-11. The preserved `06-X-oppose` capture visibly reproduced the hard stall and established healthy accumulator → successive control-yaw transfer at sampled checkpoints. The new accumulator captures validate the intervening calls during **healthy** mouse/opposing input. Repeating the heavy probe is not a prerequisite for this next boundary.

**Live view validation completed:** Both new view trials have 1200/1200 returned rotations equal to cache and zero errors. Neither reproduced the hard seizure. Five callers exhausted the limit in under one debugger host second, so this shared getter still creates many stops. Use the [new evidence, downstream map and external pose sampler](camera-pose-poll.md) next. The GDB trials below are retained as history, not a request to repeat them. `mif-view-export` now supports one-time pointer discovery followed by detached sampling.

This observer uses **one hardware execution breakpoint** after the manager view getter has copied its rotation output. Each hit reads control rotation and actual returned view rotation at the same stopped checkpoint. Rows stay buffered until capture ends. There are no accumulator watchpoints, handler probes, setter probes, inferior calls or DLL changes. GDB still stops on every getter hit, including preparation and other-manager hits before filtering. This reduces instrumentation but does not eliminate timing perturbation; merely filtering rows would not remove those stops.

Static evidence for shipping SHA-256 `b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`:

| Preferred image VA / slot | Established operation |
|---|---|
| Controller `vtable+0x7f8 → 0x14357d760` | View accessor. Its manager path loads controller `+0x350`, checks manager float `+0x1340 > 0`, and tail-jumps through manager `vtable+0x800`. Earlier/fallback paths can bypass this getter. |
| Manager `vtable+0x750 → 0x14357aa60` | Leaf returns `manager+0x1350`, preserving RCX. |
| Manager `vtable+0x800 → 0x14357aad0` | Calls the cache accessor, then copies three location doubles and three rotation doubles to the caller's output buffers. Rotation is manager `+0x1368`, yaw `+0x1370`. |
| **Checkpoint `0x14357ab0f`** | All output copies have completed. RCX is manager, RAX is cache, RDI is rotation output, and `[RSP+0x28]` is the caller's return address. RBX has already been restored. |
| Controller `vtable+0x760 → 0x1430bace0` | Separate control-rotation vector at controller `+0x310`, yaw `+0x318`. |

These are returned camera-view values, **not proof of the final rendered frame**. The getter can serve several callers, including a tail-call through the controller. Caller addresses are retained without inventing renderer labels. Later view changes and bypass paths remain outside this checkpoint. Manager float `+0x1340` is recorded as `cache_stamp`; its validity-branch use is verified, but it is not a proven frame counter. No constant control/view offset is assumed.

Static validation checks the full shipping hash, probe/guard bytes and links in two controller vtables and the manager vtable. Live discovery separately checks actual controller/manager virtual targets and rejects different implementations. The real GDB fixture executes the exact shipping getter bytes and verifies output, stack caller, new-thread hits and cleanup.

```sh
python tools/camera_view_static.py '/path/to/SteamLibrary/steamapps/common/Oblivion Remastered/OblivionRemastered/Binaries/Win64/OblivionRemastered-Win64-Shipping.exe'
python tests/camera_view.py --gdb
```

Use a **fresh GDB session**, the same production candidate/input settings, standing still on foot away from camera-mode transitions. Stop and detach the accumulator session first. A short mouse-X baseline followed by one opposing-X attempt is sufficient. If the stall remains timing-sensitive, preserve the result without requiring repeated attempts.

```sh
pgrep -af '[O]blivionRemastered-Win64-Shipping\.exe'
gdb -q -nx
```

Replace `PID` with the current game PID. If attachment is denied, use `sudo gdb -q -nx` as in the prior guide.

```gdb
set pagination off
set print thread-events off
set debuginfod enabled off
set auto-solib-add off
handle SIGUSR1 nostop noprint pass
attach PID
source tools/camera_view_capture.py
mif-camera-base
mif-view-find
continue
```

Discovery stops on the next controller view call and prints fresh validated controller/manager addresses. No mouse input is required. Do not reuse pointers from the accumulator trace. If discovery rejects a layout, preserve that message. If discovery has not stopped within about 10 seconds of gameplay, Ctrl+C and `mif-view-stop`.

```gdb
mif-view-trial 01-X-mouse
continue
```

Focus the game and move mouse X continuously. Timing begins on the first selected-manager hit: **8 seconds preparation, then 6 seconds sampling**, capped at 1200 returned-view rows. Finish is checked only on selected-manager hits. If still running after about 20 seconds, Ctrl+C and stop manually. If hardware-breakpoint insertion fails on continue, preserve the error and stop; do not substitute software breakpoints. A row is a getter call, not a frame.

```gdb
mif-view-stop
mif-view-report
mif-view-trial 02-X-oppose
continue
```

Use the prior opposing-X pattern, then stop/report again. Record whether the hard seizure occurred, approximate position within the sample, whether the other axis stayed responsive, and any release or hand-repositioning interval. Continued tugging or no symptom does not establish that the intermittent stall is fixed.

```gdb
mif-view-stop
mif-view-report
detach
quit
```

Preserve `/tmp/mif-view-LABEL-TIMESTAMP.jsonl`, `.summary.json` and `.views.csv`. Stop explicitly to flush buffered rows before quitting; killing GDB during sampling can lose them. Repeat discovery after scene/controller changes or game restart.

Compare successive checkpoints **within the same thread/controller/manager/caller**, as the report does. Control yaw advancing while returned view yaw stays flat narrows the boundary to pose production/cache consumption, if aligned with the visible symptom and not explained by camera mode. Both advancing during a visible stall points farther downstream. Different control/view angles alone are not a fault: offsets, lag and mode can be legitimate. No hits or too few hits cannot establish a frozen camera; this manager path may be bypassed. Host intervals are debugger time, not game-frame duration. A capture without the symptom remains labelled healthy.
