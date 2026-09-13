Camera investigation update, 2026-09-11. **Both new view captures are healthy controls.** The user did not reproduce the hard seizure; opposing input remained functional. Preserved `06-X-oppose` remains the only live hard-stall reproduction. Do not require repeated GDB reproduction to advance.

The view traces validate the probe and normal control path, not the getter during a stall. Raw traces, regenerated JSON/CSV reports, source paths, SHA-256 values and symptom classification are preserved under `build/camera/pose/live-2026-09-11/` (`provenance.json`).

| Observation | `01-X-mouse` | `02-X-oppose` |
|---|---:|---:|
| View returns / returned rotation equals cache | 1200 / 1200 | 1200 / 1200 |
| Errors | 0 | 0 |
| End reason | `view_limit` | `view_limit` |
| First-to-last view row, debugger host seconds | 0.782055 | 0.937687 |
| Distinct cache-stamp values | 93 | 114 |
| Caller return RVA `0x334692d` | 370 | 451 |
| Caller return RVA `0x44b3b07` | 553 | 410 |
| Caller return RVA `0x3d81875` | 93 | 113 |
| Caller return RVA `0x3327120` | 92 | 113 |
| Caller return RVA `0x3203eb2` | 92 | 113 |

The report now retains motion counts by thread/controller/manager/caller. Both control yaw and returned view yaw change across all successive same-caller checkpoints for callers `0x3327120` and `0x3203eb2` in both captures. Full control and returned rotations are not bit-identical in either healthy capture. Differences in angle or query timing alone are not a stall test.

One code location did not mean one stop per frame: the getter is queried by several paths, sometimes repeatedly for the same cache value. The hardware checkpoint still caused 1200 debugger stops in less than one host second of sampling. Distinct cache stamps are not proven frame counts, and host seconds are not measured game time. Filtering recorded callers would not remove debugger traps at a shared getter.

**Static investigation has advanced beyond the getter.** Preferred image VAs below use base `0x140000000` and the same verified shipping SHA-256 as the other guides. These are instruction-level transfers; scene/view role names are inferred from the data flow, not recovered symbols or live stall observations.

| Boundary | Established operation |
|---|---|
| `0x143346927 → 0x14334692d` | Observed caller invokes controller view accessor with location at its output structure and rotation at output `+0x18`. |
| `0x1433469c0..0x1433469d6` | **After that getter**, an optional callback loop passes the same view structure in R8 through callback `vtable+0x18`. These callbacks can alter the view after the existing probe. `0x1433469e2` is after the loop. |
| Static vtable `0x147702178` | Slot `+0x2c8 → 0x1433465d0` links that view-structure function; `+0x2e8 → 0x14333bb40` links the construction path below; `+0x360 → 0x143343260` links another projection/matrix path. Live execution of the latter paths has not been captured by this probe. |
| `0x14333bd8d → 0x14333bd93` | Construction path calls view-structure slot `+0x2c8`, then copies its location and rotation to construction inputs. Thus the optional callbacks above precede these copies. |
| `0x14333bec9 → 0x14333bece` | Calls constructor `0x143624680`. Stores at `0x1436248ef..0x14362491c` copy input location to constructed view `+0xb30`, rotation to `+0xb48` (yaw `+0xb50`). The construction caller then reads those fields into its output buffers. |
| `0x14333bf97` | Appends the constructed view pointer to the collection supplied to this path. This is not GPU submission or proof of presentation. |
| `0x14333c190..0x14333c1b4` | A **further** optional callback loop passes the constructed view in R8 through `vtable+0x10`. `0x14333c1b6` is after that loop; RBX still holds the view. |
| `0x14334341e → 0x143343424` | Another path calls view-structure slot `+0x2c8` before subsequent projection/matrix work. |

The frequent caller `0x1444b3b07` computes a squared location distance after retrieving the view; it is not evidence of one rendered frame per getter return. Caller `0x143d81875` leads into rotation/matrix arithmetic. The other caller locations and their bounded disassembly are retained under `build/camera/pose/static/`; none is labelled as final presentation without proof.

Reproduce the downstream static validation and bounded disassembly:

```sh
python tools/camera_view_static.py '/path/to/SteamLibrary/steamapps/common/Oblivion Remastered/OblivionRemastered/Binaries/Win64/OblivionRemastered-Win64-Shipping.exe' --downstream
```

It validates the shipping hash, exact byte spans in `tools/camera_view_downstream.json`, and the static virtual links. Evidence is under `build/camera/pose/static/downstream/`. No probes are installed by static validation. Callback presence, targets, effects during a stall and later render consumption remain unobserved. Nothing in the new healthy traces implicates a callback as the cause.

**Next observation without repeated debugger stops:** `camera_pose_poll.py` reads the established control/cache boundary externally through `/proc/PID/mem`, at 20 Hz for 30 seconds by default. This uses the preserved stall's healthy control-yaw boundary to ask whether the separate camera cache keeps moving during a naturally occurring symptom. It does not capture post-callback scene views, and is not represented as a final render probe.

There is no ptrace attach, target suspension, signal delivery, breakpoint, watchpoint, inferior function call, injection or DLL change during polling. The OS still enforces process-memory read permissions. The sampler reads each pose twice, retains both raw byte sets, records read duration and flags differing reads. Equal repeated bytes are **not an atomic snapshot guarantee**: updates or an ABA change can occur between reads. The report does not bridge a differing-read sample when computing motion deltas. Rows are buffered and missed deadlines are skipped rather than followed by a burst of reads. This reduces a known source of perturbation; it cannot guarantee zero timing impact.

The game PID `744265` from the supplied traces has exited. Its pointers must not be reused. On the next game session, export a fresh binding with one discovery stop; **do not run a GDB trial**. Use the normal fresh-session attach setup from the [view guide](camera-view-capture.md), then:

```gdb
source tools/camera_view_capture.py
mif-camera-base
mif-view-find
continue
```

When discovery stops in gameplay:

```gdb
mif-view-export
detach
quit
```

This prints `/tmp/mif-view-binding-TIMESTAMP.json` containing the fresh controller/manager pointers, process start ticks and boot ID. No opposing input or symptom reproduction is required for discovery. Follow the view guide's manual-stop limit if discovery does not hit; no broad search or trial is needed.

Substitute that actual binding path below. If `/proc/PID/mem` access is denied, run the same command using `sudo python`; this is process-memory read permission, not a request to attach GDB. The sampler rejects a traced/stopped process, changed process incarnation, unsupported code/virtual targets, or changed object binding.

```sh
python tools/camera_pose_poll.py /tmp/mif-view-binding-TIMESTAMP.json --check-only
python tools/camera_pose_poll.py /tmp/mif-view-binding-TIMESTAMP.json --label X-oppose --seconds 30
```

Focus the game during the default eight-second preparation period, then play with the opposing pattern. No six-trial baseline set is required. Ctrl+C saves the buffer early. Record whether and approximately when the hard seizure occurred, affected axis and any release/repositioning. If it remains absent, keep the result healthy; repeated reproduction attempts are not a prerequisite for more static investigation. Stop before scene/controller changes; export again after a restart or binding change. Killing the sampler without normal cleanup can lose buffered rows.

```sh
python tools/analyze_camera_pose_poll.py /tmp/mif-pose-poll-X-oppose-TIMESTAMP.jsonl
python tests/camera_pose_poll.py
```

The tests include a live, untraced child process advancing while its parent reads memory, plus stale-binding, process-incarnation, byte/slot, update-race and report checks. The sampler has not yet captured the game or the hard stall. A read-only preflight against the supplied trace correctly rejected the exited PID.

If control progresses while cache motion flattens during the visible symptom, investigate pose production before this cache. If both progress, focus on the mapped post-getter callback/construction/scene-view stages. For that later boundary, a bounded in-process recorder after the callback loops is a candidate to validate; adding another continuously firing GDB checkpoint would reintroduce the observed trap burden. Do not asynchronously poll a saved stack-output or transient scene-view pointer: its lifetime and update ordering are not established. The old `06-X-oppose` snapshots contain controller state, not manager pose or final scene-view bytes, so those missing stages cannot be reconstructed retrospectively.
