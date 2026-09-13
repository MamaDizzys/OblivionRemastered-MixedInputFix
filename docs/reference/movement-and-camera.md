**Camera investigation advanced beyond the shared view getter (2026-09-11).** Both live view trials validate 1200/1200 cache-to-output copies with zero errors, but neither reproduced the hard seizure. `06-X-oppose` remains the only live hard-stall reproduction and already showed healthy successive control-yaw transfer. Static tracing now reaches post-getter callbacks, constructed scene-view pose fields and further callbacks. Use the [downstream evidence and external pose sampler](../guides/camera-pose-poll.md); repeated GDB reproduction is unnecessary. The new sampler reads the established control/cache boundary without attaching or stopping during sampling, and is not a final render probe. The [accumulator evidence and baseline exceptions](../guides/camera-accumulator-capture.md) remain healthy control evidence. Production movement remains unchanged.

The hours-long diagnostic menu-exit run and subsequent production Alt+F4 run both exited cleanly. The [preserved four-event shutdown baseline](../guides/shutdown-diagnostic.md#clean-live-baseline--2026-09-08) does not establish a fix or cause; shutdown remains intermittent pending another reproduction.

Movement implementation and completed live evidence, 2026-09-07. This status supersedes the pre-capture review below. **The provenance-aware movement architecture is Live Verified** on `build/MixedInputFix-production-candidate.dll`, SHA-256 `7551c3af9193e2556af7671fbac9b6f0458753f8271430db1fac7e182a21830c`, per the user’s subsequent in-game validation. Camera conflict investigation is now active; production movement remains untouched.

**Live Verified — new production movement candidate (user report).** W/S/A/D work; Backward/Left are fixed; fractional analog is smooth; native left-stick movement continues during real mouse/gyro. The captured full-cardinal stick exact-1.0 tie can beat an opposing digital direction; fractional stick loses to digital 1.0. Two held digital directions win both axes against opposite diagonal stick components because each digital action is 1.0 and the diagonal components are fractional. Other mixed arbitration matches predictions, with no movement regression observed in normal gameplay. This is gameplay acceptance of the new candidate, distinct from the baseline JSONL evidence below. No new validation trace was supplied; this does not certify each historical release/rebind/focus/reconnect checklist item.

**Camera investigation resumed — observation only.** Independent right stick and true mouse/Steam Input gyro work; simultaneous same-direction input mostly works, but opposing input can briefly stall the affected axis while the other remains responsive. The cause is still unknown. The current source confirms that getter routing chooses a format for one dispatched value; it neither combines sources nor bypasses modifiers or response state. Movement acceptance strengthens confidence in the shared provenance infrastructure, but does not prove correct camera provenance for every live X/Y dispatch.

Prioritize these mechanisms, as hypotheses rather than findings:

| Mechanism | Distinguishing observation |
|---|---|
| Winner sign/source switches around a magnitude crossing, followed by stateful action modifiers | Mapping candidates and winning signed value stay nonzero; action-after crosses/lingers near zero while the winner tag remains the selected physical mapping. A nonzero output alternating signs could also average visually near zero without any zero-valued call |
| Camera response history or shared latest-axis contamination | Nonzero handler input and appropriate getter result, but zero/suppressed output correlated with changes to latest X/Y or retained gain; compare same-direction and isolated baselines, not raw mouse and stick units |
| Several bindings/actions emit opposite processed outputs | Count actual handler/output calls per complete generation, action, instance, binding, receiver and axis. Opposite outputs only prove cancellation if the downstream target/consumer actually accumulates and consumes them together |
| Provenance fallback or post-selection format mismatch | Compare actual getter AL with current dispatch snapshot, table record, generation, action policy/type, axis, and pre-CALL CommonInput. Source provenance survives modifiers, so even a correct tag does not certify final units |
| Downstream gate, overwrite, clamp or consumption history | Inputs, branch and handler outputs are healthy; resolved output target or its eventual consumer loses motion. Inspect that exact target only after the first capture narrows the problem |

Policy-0 max magnitude **does not arithmetically cancel opposing candidates**. Policy 1, separate actions and repeated dispatches must still be observed. Cross-generation sign alternation is different from two outputs cancelling in one generation. A momentary near-zero net rotation can be sensible opposition; persistence under clearly unequal processed inputs or after one source releases is the stronger stall diagnostic. Debugger host timestamps are not gameplay frame durations.

The first pass is six short captures: X stick alone, X mouse/gyro alone, Y stick alone, Y mouse/gyro alone, X same-direction, then X opposition. Check the first report before continuing and review the baselines before interpreting opposition; expand to release order, Y opposition and cross-axis controls only as needed. All active probes cover both axes. Exact commands, inputs, stop limits and evidence decision rules are in the [camera capture guide](../guides/camera-capture.md). No production source or DLL rebuild is involved. The old global `cmp al,0xFF` camera patch remains absent; original `cmp al,1` remains validated. No global priority or speculative additive-policy switch is proposed.

**Observer corrections for this candidate.** `tools/camera_capture_sites.json` now pins reset helper RVA `0x7A40` (158 bytes) and camera input-type helper RVA `0x9700` (405 bytes) from the matching DLL/PDB audit. Critically, linked `input_type` reads current dispatch at TLS `+0xC30`, while provenance starts at `+8`. The old manifest’s dispatch offset `0` was incorrect even though its synthetic fixture passed. Current tests must exercise the compiled offset, not repeat that assumption. The observer also resolves its own source path under GDB without relying on `__file__`, retains early unknown mapping contributions, reads CommonInput before the helper can clobber RCX, pairs output returns with their actual calls (mouse-return sites are shared epilogues), and records native handler RETs to distinguish complete no-output calls from truncated traces. A new trial command uses 8 seconds preparation then 3 seconds contiguous recording, capped at 6000 rows.

The response fields remain shared, as described in the retained static review below. This pass found no new live cause and makes no camera-fix claim.

**Live Verified — baseline candidate and raw captures.** All references below are JSONL `seq` numbers, not line numbers. Files are preserved under `build/movement-production/`; filenames and hashes are listed in `build/movement-production/capture-inventory.txt`. The first stick-left attempt contains no useful movement action evidence, and the first AD-downleft attempt ends `timed_partial`; use the successful repeats. The isolated physical keyboard trials identify the `Other` identities as W/S/A/D in that session only. Production does not embed those IDs.

| Evidence | Raw capture and examples | Consequence |
|---|---|---|
| W/D digital +1 survives; S/A +1 first writes -1, then NOP overwrite writes 0 | `01-W`, `04-D`; `02-S-1788809633295212279`, seq 11/14 winner stays +1, 39 cache B=-1, 40 B=0; `03-A-1788809710025405528`, seq 14/17 winner +1, 39 L=-1, 40 L=0 | The NOP regression is directly observed, beyond the earlier static explanation |
| Negative signed stick input feeds both opposing actions | Successful `05-stick-left-1788810343755780059`, `06-stick-back`, `07-stick-diagonal` | Left/Backward need min(v,0), Right/Forward max(v,0) for the winning stick component |
| Later gamepad -1 replaces digital +1 at an exact magnitude tie | `08-D-left-1788810907625006797`, seq 17/20 (Right); `10-AD-left`, seq 14/17 (Left), 20/23 (Right) | Preserve actual store provenance, including later-winner tie behavior; no global device priority |
| Fractional stick loses to digital 1; different actions have different owners in one evaluation | `09-D-roll`, generation 178 seq 128/131 vertical LeftY winners, 137/140 Right stays digital 1 despite LeftX=0.8933; `11-AD-back`; repeated `12-AD-downleft-1788811769072304731`, seq 8/11 vertical stick, 14/17 and 20/23 horizontal digital 1 beats ~0.8369 | Both frame-wide and axis-global ownership are insufficient; keep per-action/component provenance |
| CommonInput changes while winner stays fixed | Repeated `08-D-left`: getter/global 0 at seq 39/44, 1 at 89/94, 0 at 139/144; the horizontal winners are LeftX=-1 throughout | +0x90/+0x91 is not action provenance |
| Original mouse/gyro + fractional stick failure mechanism reproduced with no keyboard movement contribution | `13-stick-mouse-1788811916756442544`, seq 18/21 LeftX winner -0.453186; 22–25 action modifiers produce -0.356689; 40/45 getter/global 0; 41/46 NOP split yields L=-0.356689/R=0, sum seq 51=-0.356689 | The original digital interpretation would produce freshly written opposing values and cancel. The winning source must survive action modifiers |

**Static Analysis — digital metadata and production contract.** The completed captures do not contain FKeyDetails metadata; the metadata classifier is statically derived and synthetically tested, with new observer fields supplied for live confirmation. At `0x392BAE5` the physical caller passes R14 (the FKey later saved at mapping `[RBP+0x1F]`) to `0x115C1D0`. That query calls the lazy resolver `0x1134AD0`, then reads `[FKey+8]` and `[details+0x42]`. Thus production can read already-resolved details without invoking the engine or writing metadata. The details constructor `0x1133E4F` copies the full FKey identity into `[details]`; the classifier checks equality with the mapping's full eight-byte identity.

The type encoding at `0x1134A64–0x1134A90` yields 0 for a digital key, 1 for button-axis, 2 for 1D analog, 3 for 2D and 4 for 3D. The A registration passes flags 0 to the details constructor; LeftX passes 0x21 and becomes type 2. Disassemblies: physical caller (`build/movement-production/physical-mapping-caller.asm`), constructor (`build/movement-production/key-details.asm`), type encoding (`build/movement-production/key-type.asm`), analog query (`build/movement-production/key-analog-query.asm`), initializer index (`build/movement-production/key-initializers.txt`). Newly added exact signatures guard the metadata offsets, caller/query, mapped type/candidate layout and LeftX/LeftY runtime-global initializer references, as well as all four complete getter CALL displacements and branches. All 28 signatures match the shipping executable SHA-256 already recorded below.

**Implementation / standalone validation.** The architecture remains the proposed four getter CALL redirects with original `75 0F` branches intact. No extra hook is needed. The actual winning store records Digital (nonnegative finite mapped Axis1D contribution plus verified digital key details) or LeftStick X/Y (finite mapped Axis1D contribution, corresponding runtime full FName and 1D details). Unsupported or invalid winners erase earlier known winners with Unknown. The per-action entry already identifies the scalar component because only Axis1D/component 0/policy 0 is supported. Digital is axis-independent as a physical format, but its ownership is still attached to one action/instance. LeftStick must match the handler's axis. Camera tags remain distinct.

The movement getters return 0 for Digital and 1 for the corresponding LeftStick tag, requiring the same current generation, owner/frame, action/instance, supported type/policy and unchanged dispatch snapshot as camera. Otherwise they call the original getter. They leave the null-subsystem and blocking paths, action values/modifiers, consumer, cache clears and engine merge untouched. The tag survives the later action modifier stage; no magnitude-based reclassification occurs at dispatch.

**Inference / movement acceptance subsequently completed above.** These observations justify the smallest source-aware handler-format correction and do not justify a new composition algorithm. Expected mixed movement is the engine's per-action winners followed by the original direction stores and consumer sum. For example, digital A and D both winning should yield L=-v/R=+v and cancel horizontally; an axial stick winning both exact ties should yield its signed axis. This is not a claim that every simultaneous keyboard/stick input must add or that keyboard always wins. The user’s new-candidate gameplay report now confirms the movement results above. Rebound keys, focus/reconnect and other unreported checklist details remain outside that specific report. The original baseline captures prove the problem and arbitration, not execution of the new classifier.

The focused movement acceptance procedure is preserved in [MOVEMENT_CAPTURE_GUIDE.md](../guides/movement-capture.md). Its camera deferral is superseded by the resumed investigation above. The historical static review below retains its original chronology; use the new camera guide and updated observer for current commands.

The following is the historical pre-capture review. Its requests to collect movement evidence before coding have now been satisfied; its byte analysis remains useful.

---

Movement regression and simultaneous-camera review, 2026-09-06. Analysis and observing instrumentation only; production source, DLL, and reset/generation architecture are unchanged. Nothing installed into Oblivion. All addresses below are RVAs; add the actual loaded game base in GDB.

The keyboard regression has a concrete static explanation: the NOPs force a signed-axis interpretation onto positive digital direction values. Backward/Left first negate the input, then overwrite that correct negative result with `min(original_input, 0)`. Forward/Right instead use `max(original_input, 0)`, which preserves a positive digital value. Rebinding cannot change this because the error is in the logical handlers after mapping.

The shipping image used for inspection has SHA-256 `b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`. Evidence: directional handlers (`build/movement-review/handlers.asm`), movement consumer (`build/movement-review/consumer.asm`), and left-stick key initializers (`build/movement-review/left-key-initializers.asm`). This was a bounded inspection of the four handlers, their cache references, the identified consumer, and the existing mapping/camera pipeline. The prior evaluation ABI investigation was not repeated.

Each movement handler receives the object in RCX and a value pointer in RDX. After the existing blocking checks, RBX holds the object and RDI the value pointer. It clears byte `object+0xD41`, converts the first double at `[RDI]` to a float in XMM6, writes its digital-path cache value, obtains CommonInput, then optionally rewrites the cache for gamepad format. The original CommonInput getter returns byte `object+0x91`; value 1 selects the gamepad rewrite. If the subsystem lookup is null, even the current NOP candidate skips that rewrite. The blocking checks and null-subsystem path must remain intact.

For ordinary finite values, let `v` be the converted input float:

| Direction | Handler entry | Cache offset | Initial digital-path store | Branch patched to NOPs | Gamepad-path overwrite | Original JNE target |
|---|---|---|---|---|---|---|
| Backward | `0x488AB80` | `+0xD50` | `-v` at `0x488AC1F` | `0x488AC43` | `min(v,0)` at `0x488AC4C` | `0x488AC54` |
| Forward | `0x488AC80` | `+0xD4C` | `v` at `0x488AD15` | `0x488AD39` | `max(v,0)` at `0x488AD42` | `0x488AD4A` |
| Left | `0x488AD70` | `+0xD54` | `-v` at `0x488AE0F` | `0x488AE33` | `min(v,0)` at `0x488AE3C` | `0x488AE44` |
| Right | `0x488AE70` | `+0xD58` | `v` at `0x488AF05` | `0x488AF29` | `max(v,0)` at `0x488AF32` | `0x488AF3A` |

The negative handlers use XORPS with the sign-bit mask at `0x870EB30` (four `0x80000000` words). They do not negate XMM6 itself: the initial store uses XMM0 while XMM6 retains the original input. That distinction is the regression. In each handler `75 0F` means “if AL != 1, jump over the following 15-byte zero/min-or-max/store sequence.” Replacing it with `90 90` makes that sequence unconditional whenever execution reaches the comparison. It does not merely zero an opposing cache, and it does not change an input binding.

Vanilla keyboard direction actions use a positive activation magnitude; for `v=1`, Backward/Left retain `-1`, Forward/Right retain `+1` when CommonInput selects the non-gamepad path. The NOP candidate changes those results to `0, +1, 0, +1`. This fully explains the reported keyboard direction split. The handler algebra is proven from bytes; a capture of the user's actual mapping input remains useful to verify its type/modifiers and positive activation magnitude directly.

The gamepad path expects a signed axis value. If the pair of handlers receives the same signed value `s`, their outputs sum to `min(s,0)+max(s,0)=s`, preserving fractional magnitude. If CommonInput has switched away from gamepad because of mouse activity, the unpatched digital paths can instead write `-s` and `s`, producing zero. **This cancellation does not require stale values from an older evaluation:** both caches can be freshly written and still cancel. Persistent caches can contribute too, but a trace is needed to identify which mechanism occurs in a particular frame. The NOPs fix this format mismatch for analog input by creating the digital regression above.

The consumer at `0x489F635–0x489F658` computes:

```text
forward_axis = float[object+0xD50] + float[object+0xD4C]
right_axis   = float[object+0xD58] + float[object+0xD54]
```

It writes the raw pair at `object+0xA60`, derives vector length/direction, clamps magnitude to [0,1], and applies further movement scaling. It does not convert a nonzero fractional input into a digital one. A zero sum is already lost before that processing. Clear handlers at `0x488AC70`, `0x488AD60`, `0x488AE60`, and `0x488AF50` zero Backward, Forward, Left, and Right respectively. The consumer does not clear these four caches; additional object-reset paths also clear them. Do not clear every cache at the evaluation reset: doing so assumes every held direction is redispatched and risks destroying valid digital state.

Keyboard and stick do not occupy separate source slots in these caches. Each handler writes one scalar; later invocations overwrite that scalar, and the consumer adds the opposing logical-direction slots. Before dispatch, mapping aggregation can also arbitrate between keyboard and analog contributions to the same action. At `0x3934858`, policy 1 adds components. Otherwise the comparison at `0x393488B` keeps the candidate if its absolute magnitude is at least the accumulated magnitude; the later mapping wins exact ties. The production recorder handles only Axis1D/policy 0 and observes the winning store at `0x3934891`. It currently classifies only MouseX/Y and Gamepad_RightX/Y: keyboard and left-stick mappings are Unknown, so the existing table cannot already supply movement provenance.

This gives a specific explanation to test for the straight-versus-diagonal interaction: a digital magnitude of 1 can beat a stick component below 1, while a full axial stick value can tie it and win by mapping order. Diagonal stick components can be smaller than full axial components. Under the NOPs, a positive digital winner in a negative handler then becomes zero. **This is a conditional mechanism, not a finding about the user's A+D invocation order or actual deadzone/modifier output.** The capture must establish which actions receive which keys, their modified values, policy, ties, handler order, clear events, and consumer sums. It must also distinguish a single merged action from separate binding invocations. The observation alone cannot establish those facts.

The smallest replacement to investigate is **four movement getter CALL redirects with the four original JNEs restored**, using dispatch-scoped movement provenance under the existing owner/frame/generation checks:

| Direction | Existing getter CALL to redirect |
|---|---|
| Backward | `0x488AC3C` |
| Forward | `0x488AD32` |
| Left | `0x488AE2C` |
| Right | `0x488AF22` |

For a verified signed left-stick-axis winner, return 1 so the original half-axis split runs. For a verified digital movement winner, return 0 so the original sign conversion survives, even if CommonInput most recently saw the controller. Unknown, mismatched, nested-invalidated, unsupported-policy/type, or unverified value-format cases use the original getter. Do not equate Unknown with keyboard. Keep camera key classification separate so adding left-stick provenance cannot accidentally qualify a left-stick mapping as a camera source. The existing reset shim, winner store replay, dispatch scope, camera getter redirects, and original camera comparisons need no architectural change.

Static initialization identifies Gamepad_LeftX's FKey global as `0x9113ED8` and Gamepad_LeftY's as `0x9113EF0`: constructors at `0x9002E0` / `0x900320` pass their ASCII key names and those global destinations to the same FKey constructor used by RightX/Y. Compare full runtime eight-byte identities, as the current camera code does; do not hardcode observed name IDs. Digital classification still needs verified physical-key metadata or the relevant validated mapping identities, with support for rebinding. Classification must describe the value's format after mapping modifiers, not merely the nominal device.

This is the minimal candidate **for correcting the handler format choice**, not a claim that source-aware getters alone meet every mixed-source composition case. They preserve the engine's existing per-action merge, including magnitude/tie effects. If live evidence shows that a dispatched value already combines incompatible digital and signed-axis formats, a winner tag alone is insufficient. A larger alternative would normalize verified digital and stick contributions into signed directional half-axes *before* they merge, using consistent handler interpretation afterward, or retain separate source contributions. Either changes more of the movement pipeline and requires explicit mapping/order evidence. Do not implement it speculatively, flip MIN to MAX, take absolute values, clamp stick magnitude to 1, infer source from input sign, or globally force the keyboard path. None is a sound general replacement for the four NOPs.

Live GDB is **not required to establish what the four branches do or why positive keyboard values lose Backward/Left**. It **is required before implementing and claiming the source-aware replacement handles the user's mixed combinations**, since live action bindings, modifier chains, event order, and dispatched formats are not contained in these handler bytes. A new DLL is unnecessary for that evidence. [tools/movement_capture.py](../../tools/movement_capture.py) observes the unchanged current candidate with validated probe bytes, bounded event counts, and no inferior function calls or register/value edits. Software breakpoints temporarily alter instruction bytes in the normal debugger manner; no replacement behavior is installed. Do not run the camera and movement captures concurrently because their probe sites overlap.

The movement observer captures these exact sites/values:

| Sites | Capture |
|---|---|
| `0x392B69E` before reset CALL | R13 owner, RBP evaluation frame, XMM2 delta; per-thread observer generation marker (not production TLS) |
| `0x39346F0` | R14 owner, RDI instance, `[instance]` action; input at pointer `[RBP+0x67]`; physical key pointer `[RBP+0x1F]` and full FName; mapping caller `[RBP+0x3F]`, saved evaluation frame `[RBP+0x37]` |
| `0x3934858` / `0x3934897` | Before/after merge: component RCX, candidate double `[RBP-0x49+8*RCX]`, accumulated double `[RBP-0x69+8*RCX]`, action policy byte `[action+0x51]` |
| `0x392C494` / `0x392C4E4` | Action value before/after action modifiers, instance at RDI+8 |
| `0x392CD15` / `0x392CD1B` | Binding RCX, instance RDX, full value at instance+0x38, type at +0x50, virtual target; correlate synchronous dispatch entry/return by thread, RSP, frame |
| Four handler entries in first table | RCX object, RDX full input value, return address, all four caches |
| `0x488AC41`, `0x488AD37`, `0x488AE31`, `0x488AF27` | XMM6 original float, AL getter result, CommonInput object/byte, caches after initial store and before forced rewrite |
| `0x488AC54`, `0x488AD4A`, `0x488AE44`, `0x488AF3A` | Caches after optional overwrite; RBX object |
| Four clear handlers above | RCX object, pre-clear caches, return address; the following instruction zeros the specified slot |
| `0x489F635`, `0x489F65B`, `0x489F79C` | RDI object and caches; at sum site XMM2.low-double forward and XMM3.low-double right; at final site XMM0.low-double scaled forward and XMM3.low-double scaled right |

All mapping events are retained, including unidentified keys labelled Other, so identifying a movement action at its handler does not discard its earlier mapping history. Other does not mean keyboard. Short isolated-key trials identify the relevant raw identities without assuming WASD bindings. Captures include first/last partial evaluations; compare complete reset-to-reset windows. Event limits stop the inferior and remove the observer's breakpoints. GDB timing changes mean captures establish value/order relationships, not normal-frame durations.

With the game already attached and stopped, verify its actual loaded base. The following uses the previously observed `0x140000000`; substitute a different base if ASLR moved it. Output must be a new file, and the directory must exist:

```gdb
source tools/movement_capture.py
mif-move-start 0x140000000 /tmp/mif-move-backward.jsonl 12000
mif-move-mark keyboard-backward-only
continue
# Interrupt after the short trial if the event limit has not already stopped it.
mif-move-stop
```

Repeat into separate files: each logical keyboard direction alone including release; rebound Backward/Left; partial/full stick in all four directions and down-left, with and without real mouse movement; A+D alone, then A+D plus straight left/backward/down-left; W+S plus stick; each keyboard direction plus agreeing and opposing partial stick, followed by both release orders. Start from released controls for a baseline, then hold inputs long enough to include complete evaluations. The first capture priority is Backward-only and A+D plus the three reported stick cases, not an exhaustive gameplay retest.

Camera's preliminary findings remain separate from the movement fix. The max merge compares **absolute magnitudes** and stores the selected signed candidate; it does not add opposite mouse/stick values under policy 0. For example, +0.6 and -0.7 produce -0.7 at that merge, not -0.1 or zero. Ties select the later candidate. Policy 1 does sum, and the production camera override deliberately declines that policy. Per-axis winner provenance currently chooses only the camera branch; it never rewrites the action value or camera output.

That winner is recorded before the later action-modifier call at `0x392C4D0`, whose result is copied back to the action instance before dispatch. Therefore branch provenance can identify the max-winning physical mapping while the dispatched value has subsequently changed. A smoothing modifier could retain history or pass through zero on sign reversals, but the active modifiers and their history have not been captured. A provenance tag does not prove the dispatched value still equals the winning raw mapping sample.

The dispatch site is inside a binding loop (`0x392CD22–0x392CD29`). The wrapper executes each original virtual call exactly once, which does **not** prove a logical camera action is dispatched only once per evaluation. Count by thread/generation/owner/frame/action/instance/binding, then correlate actual X/Y handler calls. One merged action, multiple bindings for one action, and separate mouse/stick actions are different cases.

The camera handlers do retain persistent object state, but the inspected fields are **shared latest X/Y samples**, not two complete mouse/gamepad sample banks. Both branches enter through the same handler: X writes the converted action value to `object+0xD64` at `0x489D238`; Y writes `+0xD68` at `0x488A028`. The gamepad path reads both latest-axis fields when calculating response (X reads them at `0x489D353/0x489D35B`). Thus per-axis dispatch provenance does not make these existing engine fields source-pure. The gamepad paths also update persistent response factors at `+0xD60` (X) and `+0xD5C` (Y); the mouse paths bypass that update, leaving those factors retained. The separate clears at `0x489DB80` / `0x488A970` zero latest X/Y. This establishes some retained state, not the cause of the reported stall or the absence of state inside modifier/downstream objects.

Capture with the existing [camera observer](../../tools/camera_capture.py), in a separate run:

```gdb
source tools/camera_capture.py
mif-camera-start 0x140000000 /tmp/mif-camera-opposing-x.jsonl 12000
mif-camera-mark opposing-x
continue
# Interrupt after the short trial if still running.
mif-camera-stop
```

Use independent X-only/Y-only baselines, compatible inputs, opposing unequal inputs, near ties, and each release order. It already captures merge before/after, action modifiers before/after, production TLS generation/winner/dispatch scope, camera handler input, getter branch, persistent fields and output values. Final X output CALLs are `0x489D8C9` (gamepad) / `0x489DB05` (mouse); Y CALLs are `0x488A6B9` / `0x488A8F5`. RCX is the receiver and XMM1.low-float the output. Return probes at `0x489D8CF`, `0x489DB0B`, `0x488A6BF`, and `0x488A8FB` capture receiver state after the downstream call. The observer resolves the live receiver's virtual slot +0xD18 for X or +0xD10 for Y, records its code and receiver snapshots, and thereby supplies the exact target for any necessary follow-up accumulator probes. Do not assume that adding logged output values reproduces the downstream engine accumulator until that target's behavior is established.

Locate the first divergence: nonzero merged winner becoming near-zero after action modifiers; a changed branch's response producing near-zero output; or multiple opposite outputs cancelling in the downstream accumulator. If none occurs, follow the resolved output target's state/consumer. Opposite directions distinguish signed cancellation or sign-transition history from a global device gate, but do not by themselves choose among those mechanisms. X and Y must be analyzed independently, while observing the engine's existing cross-axis response reads. No global source priority is justified. Simply changing the action policy to additive is also premature: mouse delta and stick rate pass through different scaling/state paths, and a single selected branch may not interpret a raw sum correctly. If separate processed outputs can safely accumulate, composing them at their common angular-output stage is a candidate to assess after capture; this report does not assert that such composition is already safe.

Validation for this review: shipping signatures and observing-site bytes checked against the on-disk image; synthetic observer tests cover value/cache decoding, dispatch correlation, nested generation markers, mapping stack offsets, full key identity, sum registers, and fail-stop reads; Python compilation and actual GDB command loading pass. These are instrumentation checks, not a live fix validation. The production DLL still hashes to `0a945b1ce600abe54de83bc1ba9f37df55149cbe051d97d109157f07bd95a053`. No production rebuild or installation was performed.
