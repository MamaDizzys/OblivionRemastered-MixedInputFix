**Movement architecture: Live Verified, 2026-09-07**, on candidate SHA-256 `7551c3af9193e2556af7671fbac9b6f0458753f8271430db1fac7e182a21830c`. User results: all W/S/A/D directions work; fractional analog remains smooth, including during real mouse/gyro; exact cardinal ties can favor stick, fractional stick loses to digital 1.0, and two digital directions beat fractional opposite diagonal components. Mixed arbitration behaves as predicted, with no normal-gameplay movement regression observed. This supersedes the pending acceptance and camera deferral instructions below. Do not rerun movement as a prerequisite. Camera composition was subsequently implemented and live-validated on both axes; see [movement-and-camera.md](../reference/movement-and-camera.md) for the final v1.0.0 architecture and status.

The remaining content is the preserved acceptance checklist and historical baseline procedure; unreported checklist items are not automatically claimed as passed.

---

Movement candidate acceptance run, 2026-09-07. The original capture campaign is complete. **Use the newly built DLL for this validation**, SHA-256 `7551c3af9193e2556af7671fbac9b6f0458753f8271430db1fac7e182a21830c`. Nothing has been installed automatically. Start a fresh game process with this candidate as the single MixedInputFix DLL; do not load it alongside the old NOP candidate. Its signature checks require original game branches before installation.

First verify the candidate reaches the main menu and that its diagnostic log reports `four provenance-aware movement getters; original branches intact`. On foot in an open area, run these focused checks in order. Camera conflict investigation remains deferred even if its known stall can still be reproduced.

| Check | Input | Expected acceptance result |
|---|---|---|
| Digital regression and rebinding | W/S/A/D separately, then release; rebind Backward and Left to other digital keys and repeat. Also let controller activity select gamepad prompts while a digital movement key stays held | Each logical direction works; S/A retain a negative cache and clear normally on release. A digital winning action selects getter=0 even if CommonInput=1 |
| Original mixed-input bug | No movement keys; hold a fractional left/backward stick value while continuously moving the real mouse or gyro, then try full axes and diagonals | Stick-owned actions select getter=1 even if CommonInput=0. Negative LeftX: L=v/R=0; negative LeftY: B=v/F=0. Fractional magnitude survives; no freshly written +/- cancellation |
| Winner transitions and independent actions | D plus rotating stick; D plus exact full-left; A+D plus straight left, backward and down-left | Each action follows its own actual winning mapping. Digital 1 beats a fractional component; a later stick -1 wins an exact tie. Vertical stick ownership can coexist with horizontal digital ownership. Do not judge this as a global keyboard/stick priority |
| Release and reset | Repeat mixed cases releasing keyboard first and stick first; A+D and W+S alone; menu/focus transition; swap saves; disconnect/reconnect controller | No stuck direction or old winner after release/reset. Pure opposing digital directions cancel when both are active with equal values. Continued movement works after each transition |
| Short regression smoke | Swimming, horseback, native right-stick camera alone, mouse/gyro camera alone | Existing supported behavior remains usable. Record any camera-conflict observation separately; do not begin that investigation yet |

For a concise first report, send startup, S-only, A-only, fractional-left + mouse/gyro, and D + rotating/full-left results. If those pass, finish the release/reset and short gameplay checks. This is live acceptance of the new build, not a rerun of the entire baseline campaign.

If numeric confirmation is needed, attach GDB using the PID and SIGUSR1 commands in the historical procedure below, then:

```gdb
source tools/movement_capture.py
mif-move-base
mif-move-trial verify-S
continue
# Observer stops automatically after preparation/sampling; then:
mif-move-report
```

No `__file__` assignment is needed. Use a fresh GDB session if the old version of the observer was previously loaded. Repeat one trial at a time with labels `verify-A`, `verify-stick-mouse`, `verify-D-roll`, `verify-D-left`, `verify-AD-back`, `verify-AD-downleft`. The existing 8-second preparation, 3-second sparse sampling and 900-event limit remain. Report output stays capped at 150 lines; preserve the full JSONL if truncated. Do not run movement and camera observers together.

New raw capture headers record the actual movement branch bytes: all four should be `750f` for this candidate, rather than baseline `9090`. Site validation is not a full loaded-DLL hash; confirm the installed artifact separately. New mapping rows include `key_metadata`: matching identity and type 0 for digital, type 2 for LeftX/LeftY. Missing/invalid metadata is a fallback case, not evidence of keyboard ownership. The report shows this on MAP rows. Compare each action's **last actual magnitude winner** with its dispatch and getter; do not simply choose the last mapping event, since losing candidates are also recorded. Old baseline files lack metadata fields and remain valid evidence of their observed values/order.

The four pre-getter probes save CommonInput's RCX before any C++ helper can clobber it; branch rows report actual AL and the saved object's +0x91 independently. After handler execution, inspect final caches and consumer sums. For positive S/A digital winners, expect initial and final caches both negative. For stick-owned actions while global=0, expect getter=1 and the correct signed half-axis split. Action modifiers may make dispatch magnitude differ from the merge value; ownership must remain unchanged.

The following is the archived baseline capture campaign. Its instruction to keep the old installed DLL was for evidence collection and is superseded by the candidate acceptance run above.

---

Use the currently installed production candidate. No DLL change or installation is needed. Only the observing Python tools changed. Capture movement only, one trial per file; start with **W only** and return its report before doing the rest.

Put the character on foot in a flat, open gameplay area with no menu open. Use windowed/borderless mode if convenient. Avoid accidental stick/gyro input during keyboard-only trials. Keep the current bindings; mention any WASD rebinding with your report.

In a Linux terminal, find the running game's PID:

```sh
pgrep -af '[O]blivionRemastered-Win64-Shipping\.exe'
gdb -q -nx
```

Use the PID at the beginning of the actual shipping-game process row. If several rows appear and you cannot distinguish the game from Steam/Proton launchers, paste those rows first. At the `(gdb)` prompt, replace `PID` below with that number:

```gdb
set pagination off
set print thread-events off
set debuginfod enabled off
set auto-solib-add off
handle SIGUSR1 nostop noprint pass
attach PID
source tools/movement_capture.py
mif-move-base
```

The SIGUSR1 command lets Wine/Proton receive the signal while preventing GDB from stopping or printing for it. The game pauses on attach. `mif-move-base` must print `Validated movement probe bytes; $mif_base = ...`. It checks the loaded game mapping and observer sites; it does not guess the base or hash the full loaded DLL. If validation fails, stop here and paste the error plus `info proc mappings` output. If attach says `ptrace: Operation not permitted`, quit that unattached GDB, run `sudo gdb -q -nx`, and repeat the GDB commands. No system-wide ptrace setting change is needed.

For trial 01, enter:

```gdb
mif-move-trial 01-W
continue
```

Immediately return focus to the game and hold **W only**. The first running probe starts an **8-second preparation interval**, during which no input events are recorded. Keep holding W throughout the following **3-second sampling interval**, until the game freezes automatically. This is roughly 11 seconds from continuing, with up to 2 extra seconds allowed to finish or time out an incomplete window. Release W after it freezes. Do not switch focus during the sample.

Return to GDB and run:

```gdb
mif-move-stop
mif-move-report
```

`mif-move-stop` is harmless if automatic stopping already closed the capture. If the game has not stopped after about 15 seconds, switch to GDB, press **Ctrl+C**, then run the same two commands. Paste any error/stop message and everything from `MIF MOVE REPORT` through `END MIF MOVE REPORT`. Add one sentence describing what the character did. For trial 01, that means whether W moved forward normally. Send this first report before proceeding.

The raw file has a unique `/tmp/mif-move-01-W-...jsonl` name printed in the report. Keep it. The observer records about one reset-to-reset evaluation window per second, with a hard cap of 900 event rows plus closing bookkeeping. It does not print per-event logs. The report is capped at 150 lines and retains chronological movement mapping/merge/dispatch/cache evidence. `Other` is a physical key not among the six named analog/mouse globals; it is not a finding that the source is unknown to the engine or necessarily keyboard. The isolated keyboard trials identify those physical-key identities.

For subsequent trials, first reset physical input: with capture closed, run `continue`, focus the game, release all keys and center the stick, and wait 2 seconds. Return to GDB and press Ctrl+C. Then use the same pair of commands, substituting the next label:

```gdb
mif-move-trial 02-S
continue
```

Each `mif-move-trial` closes any preceding observer capture and creates a fresh uniquely named file. It resets only observer bookkeeping, never game caches or production provenance. For every trial, use `mif-move-stop` then `mif-move-report` after it stops, and paste the whole report plus the specified observation. Do not batch trials or put several input combinations in one file.

| Label | Exact input | Timing | Evidence captured / observation to add |
|---|---|---|---|
| `01-W` | W only; stick centered, no mouse/gyro | Hold during preparation and all 3 sampled seconds | Physical key, Forward action/mapping, merge and cache result; say whether forward works |
| `02-S` | S only; stick centered, no mouse/gyro | Same | Backward digital value before/after forced rewrite; say whether backward fails |
| `03-A` | A only; stick centered, no mouse/gyro | Same | Left digital value before/after forced rewrite; say whether left fails |
| `04-D` | D only; stick centered, no mouse/gyro | Same | Right digital value, merge and cache result; say whether right works |
| `05-stick-left` | Left stick against the rim directly left (9 o'clock); no keys/mouse/gyro | Same | LeftX signed values entering both horizontal handlers, mapping order and sum; describe direction |
| `06-stick-back` | Left stick against the rim straight down/backward (6 o'clock); no keys/mouse/gyro | Same | LeftY values entering both longitudinal handlers and sum; describe direction |
| `07-stick-diagonal` | Left stick against the rim halfway between left and down (7:30); no keys/mouse/gyro | Same | Actual X/Y component magnitudes and four-cache result; say whether down-left works |
| `08-D-left` | Hold D and full stick left (9 o'clock); no mouse/gyro | Same | Digital/stick magnitude ties, ordering, selected value and resulting movement; describe direction/stall |
| `09-D-roll` | Hold D and full stick left. Roll along the rim toward 7:30, keeping D held | Stay full-left during first 8 seconds after continuing; roll over next 2 seconds, then hold down-left for the last sampled second | Samples of the tie and fractional-component transition; say where movement changed. Sparse sampling may miss the exact threshold |
| `10-AD-left` | Hold A+D together and full stick left; no mouse/gyro | Hold during preparation and all 3 sampled seconds | Both digital mappings versus LeftX, order and horizontal sum; say whether straight left works |
| `11-AD-back` | Hold A+D together and full stick backward; no mouse/gyro | Same | Horizontal digital combination alongside LeftY; say whether straight backward works |
| `12-AD-diagonal` | Hold A+D together and full stick down-left; no mouse/gyro | Same | Both-axis winners/caches compared with the preceding two trials; describe diagonal failure or actual direction |
| `13-stick-mouse` | Hold left stick halfway left, approximately half its travel. Keep moving the real mouse gently left/right, or supply mouse-emulating gyro; no keyboard movement or right-stick camera input | Establish stick and mouse motion during preparation; maintain them throughout all 3 sampled seconds | Fractional LeftX, mouse mapping activity, CommonInput getter values, caches and movement sum; say whether analog movement remains smooth |

The three A+D cases deliberately use separate captures. Trial 13 observes the original mixed-input scenario with the fix installed; do not disable the DLL to reproduce the old bug. Use the real mouse if enabling gyro also produces right-stick input.

If the report says `event_limit`, `complete=False`, `NO movement action`, `REPORT TRUNCATED`, or gives a read error, paste it as-is and keep the raw file. Those flags prevent treating missing evidence as a gameplay result; we can adjust the next single trial after inspecting it. GDB breakpoints slow execution, so wall-clock smoothness during capture is not a performance measurement.

To finish cleanly, return to GDB and press Ctrl+C if the inferior is still running, then:

```gdb
mif-move-stop
detach
quit
```

Release game controls before detaching. `detach` resumes the game; it does not kill it. The observer removes its own breakpoints, and GDB removes any remaining debugger breakpoints on detach. Do not use `kill`.

After the live reports are available, compare mapping format and order through action modifiers, dispatch, handler stores, and consumer sums. Report whether movement-specific provenance getters suffice and specify the exact replacement design before any production implementation change. Camera stall investigation remains deferred.
