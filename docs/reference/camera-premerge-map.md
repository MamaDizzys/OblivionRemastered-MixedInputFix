# Camera contributions before winner collapse

2026-09-11. Analysis and proposal only; no implementation, DLL rebuild, installation, or movement changes.

**Result:** the useful boundary is the return from mapping modifiers at **`0x14393475C`**, before the nonzero test and max merge. The immediate comparison boundary **`0x143934858` / `0x143934876`** also exposes every nonzero candidate, including losers. The existing hook at **`0x143934891`** sees only winning stores. Preserve camera candidates before that hook, then run mouse and stick through their respective native camera processing, allowing their processed outputs to use the existing angular accumulator.

The smallest candidate for the observed configuration is **a camera contribution side table plus camera-handler fan-out**, with source-specific latest-axis state. It does not require changing action accumulation policy or splitting movement actions. General support for stateful action modifiers/triggers would require separate source action state; that is a larger alternative, not a requirement established by the current camera captures.

**Evidence labels used throughout**

- **Live Verified:** the user's current manual findings, or an explicitly identified archived live capture. No new game session was observed in this pass.
- **Static Verified:** instructions/data links re-read from the exact shipping executable, or explicitly identified current mod source. Descriptive structure names are not recovered C++ symbols.
- **Inference:** a consequence or semantic interpretation of those observations, with its limits stated.
- **Proposed:** intended architecture; not implemented or live-validated.

All addresses below are preferred-image **VAs**, using base `0x140000000`; subtract that base for RVAs. Shipping SHA-256: `b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`. Fresh disassemblies, ranges, and extracted live evidence are in `../../build/camera/premerge-static/`. `../../build/camera/premerge-static/validation.json` identifies the executable and ranges. These are local evidence artifacts under ignored `build/`, not checked-in source dependencies.

**Live Verified — accepted diagnosis and useful archived evidence**

The user's current manual results establish Mouse X versus Gamepad_RightX and Mouse Y versus Gamepad_RightY competition, no cross-axis interference in those trials, and a substantially lower mouse-speed takeover threshold at half-stick than full-stick. Downstream accumulator/control/view paths are accepted as previously validated healthy. This task does not reopen those investigations.

Re-reading the seven archived `build/camera/live-2026-09-08/*.jsonl` trials adds two concrete constraints:

| Live observation | Evidence | Scope |
|---|---|---|
| One X action receives both MouseX and Gamepad_RightX; one Y action receives both MouseY and Gamepad_RightY | Captured actions `0x131812600` and `0x131812800`, respectively; handler dispatch scopes connect them to X/Y handlers | Runtime identities in that process only; never hardcode these pointers |
| Camera action modifiers are empty | **1,426 camera `action_before` rows, all `modifiers.count == 0`** across the seven trials | Does not establish empty mapping modifiers, empty triggers, or unchanged configuration in a later session |
| Opposing contributions exist separately before max arbitration | `06-X-oppose`, generation 32930, seq 1235–1240: MouseX incoming `-20`, mapped `-5.600000023841858`; RightX incoming `0.2459181547164917`, mapped `0.057397689670324326` | Both target the same X action/instance; the stick candidate loses and the accumulated value stays `-5.600000023841858` |
| The selected value survives the empty action-modifier stage into dispatch | Same frame, seq 1261/1262/1269 | No action-stage smoothing is needed to explain this frame's discarded stick contribution |

The compact extraction is `../../build/camera/premerge-static/live-evidence.json`; its entries identify the original JSONL files and sequence numbers. Earlier general concerns about action smoothing must not be presented as a demonstrated active camera modifier in these captures.

**Static Verified — structures and identities**

Use `O` for the Enhanced Input evaluation owner, `M` for one mapping record, `A` for an action object, `I` for its runtime instance, and `H` for the camera-handler receiver. These names describe roles proven by the accesses below.

| Object / location | Layout or meaning established by instructions | Evidence |
|---|---|---|
| `O+0x548`, `O+0x550` | Mapping array data pointer and count; iteration stride **`0x50`** | `0x14392B721–0x14392B774`, `0x14392BCDB–0x14392BCEB` |
| `M+0x00`, `M+0x08` | Pointer-array data/count passed to mapping trigger evaluation | Caller places `M` in outgoing stack arg 8 at `0x14392BC6D`; callee loads `[rbp+0x7F]` |
| `M+0x10`, `M+0x18` | Pointer-array data/count passed to mapping modifier evaluation | Caller passes `M+0x10` at `0x14392BC75`; callee loads `[rbp+0x77]` |
| `M+0x20` | Action pointer `A` | Evaluation `R14=M+0x28`; `[r14-8]` becomes mapping-call RDX at `0x14392BC69` |
| `M+0x28` | Physical FKey: eight-byte runtime name identity, followed by details/shared-reference fields | Evaluation hashes/looks up this key; mapping frame retains the key pointer as saved caller R14 |
| `M+0x40`, bit 0 | Mapping flag consulted with key state before evaluation; an active branch skips the mapping | `0x14392BA55–0x14392BA76`, skip to `0x14392BCC1`; exact field name not assigned |
| `O+0x2F0` | Physical-key lookup container; located entries have stride `0x110`, and the value begins at entry `+0x18` | `0x14392B9E4–0x14392BA52`; additional fallback/state logic precedes the mapping call |
| `O+0x5A8` | Action-keyed runtime-instance container; entry stride `0x70`, map key at entry `+0`, `I=entry+8` | Lookup/create `0x14392E330`; found-instance return at `0x14392E3C8–0x14392E3D5` |
| `O+0x5F8` | Per-evaluation touched-action set | Reset CALL `0x14392B6A6`; mapping lookup/insertion `0x1439345A4–0x1439346D3` |
| `I+0x00` | Action pointer `A` | Mapping/policy/dispatch accesses; initialized at `0x14392323F` |
| `I+0x09…+0x11` | Mapping trigger aggregation/tracker bytes | Updated at `0x1439349F4–0x1439349FD`; not a per-source value bank |
| `I+0x18`, `I+0x20` | Action trigger pointer array and count | Action evaluation uses map-entry `+0x20`, i.e. `I+0x18`, at `0x14392C598` |
| `I+0x28`, `I+0x30` | Action modifier pointer array and count | Action evaluation uses map-entry `+0x30`, i.e. `I+0x28`, at `0x14392C498` |
| `I+0x38/+0x40/+0x48`, `I+0x50` | Three double components and one-byte value type; type 1 is the supported scalar axis path | Mapping stores `0x1439348D1/+8D9`; binding reads `0x14392D975/+D979` |
| `A+0x50`, `A+0x51` | Configured value type and accumulation policy | Constructor `0x14392329F`; mapping policy load `0x1439347DC` |
| `A+0x58`, `A+0x68` | Action trigger and modifier template arrays, respectively | Constructor builds instance arrays using per-element calls at `0x143923350/+33BE` |

**Inference:** these layouts correspond to Enhanced Input mapping/action-instance/value/trigger-tracker roles. Treating the constructor's object-creation calls as arbitrary byte-copy operations would be unsafe; owning arrays and mutable modifier objects cannot be duplicated merely by copying the instance's scalar bytes.

The full runtime FName globals used by the existing classifier are MouseX **`0x1491132C0`**, MouseY **`0x1491132D8`**, Gamepad_RightX **`0x149113F20`**, and Gamepad_RightY **`0x149113F38`**. **Static Verified — mod source:** [Sites.hpp](../../src/Sites.hpp) / [dllmain.cpp](../../src/dllmain.cpp) compare full eight-byte identities, not value magnitude or a fixed numeric name index. Those keys must additionally be tied to the recognized camera action/binding; a physical key alone does not establish camera semantics.

**Static Verified — physical mapping call and frame contract**

Evaluation `0x14392B630` calls mapping routine `0x143934550` at **`0x14392BCBA`**, returning to **`0x14392BCBF`**. Its relevant arguments at that physical call are:

| Argument | Value |
|---|---|
| RCX | `O` |
| RDX | `A=M.action` |
| XMM2.low float | Evaluation-derived time step, preserved as mapping XMM9; not assumed identical to raw frame delta |
| R9B | Evaluation pause flag |
| Outgoing `[rsp+0x20]` | Pointer to the caller's temporary input value |
| Outgoing `[rsp+0x28]` | Activity/state byte computed from key state |
| Outgoing `[rsp+0x30]` | `M+0x10`, mapping modifier array header |
| Outgoing `[rsp+0x38]` | `M`, mapping trigger array header |

At mapping entry let `S=entry RSP`; the routine sets `RBP=S-0x3F`. Consequently:

| Mapping-frame location | Identity / contents |
|---|---|
| R14 | `O` after the prologue |
| RDI | `I`, returned by action lookup/create at `0x143934581` |
| `[rbp+0x1F]` | Saved **caller R14 = `M+0x28` physical key pointer**; it is not a separately declared argument |
| `[rbp+0x37]` | Saved evaluation RBP |
| `[rbp+0x3F]` | Mapping return address; only `0x14392BCBF` proves this physical caller layout |
| `[rbp+0x4F]` | Saved action argument `A` |
| `[rbp+0x67]` | Incoming-value pointer |
| `[rbp+0x6F]` | Activity/state argument |
| `[rbp+0x77]`, `[rbp+0x7F]` | Mapping modifier and trigger header pointers |

Other callers must not inherit this physical-key interpretation. The same evaluator also calls the mapping routine on other paths; existing provenance intentionally treats foreign callers as Unknown.

**Static Verified — where contributions remain separate**

| Boundary | Exact operation and available values | Usefulness |
|---|---|---|
| `0x14393468C–0x14393469B` | Activity/trigger flags decide whether this mapping runs value processing | A skipped mapping will not hit the later candidate boundary |
| `0x1439346D8–0x1439346EB` | First touched mapping resets the instance's three value components | This is per-action initialization, not independent mouse/stick storage |
| `0x1439346F0–0x143934735` | Read incoming value through `[rbp+0x67]`; coerce to `I`'s value type, zero unused components | Still one physical mapping's contribution |
| **CALL `0x143934757 → 0x143927920`** | Apply this mapping's modifier chain | `RCX=O`, `RDX=&[rbp-0x49]` output, `R8=[rbp+0x77]` array, `R9=&[rbp-0x69]` input copy, outgoing stack `+0x20` time step |
| **Return `0x14393475C`** | **Full modified candidate is `[rbp-0x49]` (three doubles; type at `rbp-0x31`)** | Best retention boundary: physical identity intact, native mapping processing complete, zero candidates still visible |
| `0x14393475C–0x143934784` | Candidate copied into XMM7/XMM8 and a temporary; mapping triggers called at `0x143934784 → 0x14392D780` | Trigger evaluation operates on a copy; candidate is retained in nonvolatile registers across the call |
| `0x143934789–0x14393481B` | Compute magnitude/state; zero candidate bypasses numerical merge to `0x1439348DD` | A collector only at merge misses these zeros; trigger processing has its own state path |
| `0x143934821–0x143934848` | Read `I+0x38` accumulator into `[rbp-0x69]`; copy candidate back to `[rbp-0x49]` | **Both current candidate and accumulated value coexist** |
| **`0x143934858` / `0x143934876`** | Component index RCX; candidate double `[rbp-0x49+8*rcx]`; accumulated double `[rbp-0x69+8*rcx]`; policy R8D | Last convenient boundary before max comparison; camera Axis1D uses component 0 |
| `0x143934862–0x14393486E` | Policy 1 adds candidate to accumulator | Existing code does not provide a source-specific interpretation for such a sum |
| `0x143934876–0x14393488F` | Load candidate into XMM2, mask signs for comparison, branch past store if candidate magnitude is smaller | For finite inputs, later mapping wins equal magnitudes |
| **`0x143934891`** | `movsd [rbp+rcx*8-0x69],xmm2` | Winning store only; existing mod recorder is here |
| `0x143934897` | Loop continuation after either win or loss | Candidate still in scratch, but before-compare collection is clearer and also observes winners before overwrite |
| `0x1439348A8–0x1439348D9` | Repackage merged value, coerce dimensions, write back to `I+0x38/+0x48` | Candidate scratch is overwritten by the merged result; there is no durable loser list in `I` |
| `0x1439348FE–0x1439349FD` | Combine mapping trigger tracker with instance tracker independently of the winner store | Trigger state is not simply “the winning mapping's trigger state” |

The temporary at **`rbp-0x69` changes roles**: modifier input copy, then trigger input copy, then accumulated action value. Calling it an accumulator before `0x143934848` would be incorrect.

**Inference:** at the second competing mapping's comparison, both source values may be visible as candidate and prior accumulator, but that is not a general two-source structure. Earlier candidates can already have lost; duplicate mappings, other keys, skipped paths and zeros prevent reconstructing complete source contributions from the final winner. Collect each eligible mapping independently, keyed by evaluation/action/source, before collapse.

**Static Verified — remaining action and camera path**

```text
physical key state, keyed by FKey
  -> mapping record M (distinct key, modifier array, trigger array)
  -> 0x143934550: coerce value; mapping modifiers at 0x143934757
  -> separate processed candidate at 0x14393475C
  -> mapping trigger evaluation at 0x143934784
  -> per-action component max at 0x143934876 / winning store 0x143934891
  -> one I.value at I+0x38
  -> action modifiers at 0x14392C4D0
  -> action trigger/state/paused/event processing at 0x14392C594 onward
  -> selected binding at 0x14392CD18
  -> reflected binding execution; native camera value wrapper
  -> X handler 0x14489D210 / Y handler 0x14488A000
  -> source-specific native branch and scaling
  -> virtual yaw/pitch add, shared angular accumulator
```

Both mapping and action modifiers use **`0x143927920`**. It copies the input, walks the array in order, executes each non-null object's virtual `+0x268` entry with a parameter block, then coerces the returned value to the original input type. This preserves the possibility of stateful or reflected modifiers; it is not a fixed multiply that can be safely reapplied to a guessed raw value.

At **`0x14392C4D0`**, RDI is the **map entry**, so `I=RDI+8`; source and destination offsets must account for that difference. The call uses `I+0x28`'s modifier array, then copies its returned value back at `0x14392C4D8/+C4E0`. Action triggers run at **`0x14392C5BF → 0x14392D780`** with `I+0x18`'s array. Event transitions, pause handling, and binding selection precede dispatch. Bypassing all of this with unconditional extra camera calls would not preserve activation semantics.

At **`0x14392CD15`**, RCX is a binding and RDX is `I`; actual shipping virtual CALL is **`0x14392CD18`**, slot `binding.vtable+8`. This sits inside a binding loop. **Live Verified:** the archived camera dispatch target is `0x14392D940`. **Static Verified:** that target copies `I.value` only when `I+0x13 == 1`, otherwise constructs a zero typed value; it packages the action and timing fields, resolves a reflected function, and executes virtual `+0x268` at `0x14392DA56`. The dynamically selected reflected function is not statically determined by that instruction alone.

Two native value wrappers are statically connected to the camera handlers:

| Native wrapper | Camera CALL | Handler | Clear wrapper / destination |
|---|---|---|---|
| `0x144641B30` | **`0x144641BC8`** | X `0x14489D210` | `0x144641BE0`, tail JMP at `0x144641BF5 → 0x14489DB80` |
| `0x144640980` | **`0x144640A18`** | Y `0x14488A000` | `0x144640A30`, tail JMP at `0x144640A45 → 0x14488A970` |

These wrappers decode a typed value and call the handlers with **RCX=`H`, RDX=value pointer**. A direct-call scan found these two handler CALLs; this is not proof that no indirect caller exists. **Inference:** the archived synchronous binding-to-handler observations and the native wrapper code fit the reflected call chain; no new live instruction trace through the reflected middle was collected.

**Static Verified — source processing, state and additive destination**

| Operation | X / yaw | Y / pitch |
|---|---|---|
| Entry converts input double to float, writes latest sample | `0x14489D238`, `H+0xD64` | `0x14488A028`, `H+0xD68` |
| CommonInput getter CALL redirected by current mod | `0x14489D2F9` | `0x14488A0E9` |
| Original `cmp al,1` chooses stick branch | `0x14489D2FE` | `0x14488A0EE` |
| Stick response factor | `H+0xD60` | `H+0xD5C` |
| Stick final output CALL | `0x14489D8C9`, vtable `+0xD18` | `0x14488A6B9`, vtable `+0xD10` |
| Mouse final output CALL | `0x14489DB05`, vtable `+0xD18` | `0x14488A8F5`, vtable `+0xD10` |
| Latest sample clear | `0x14489DB80` | `0x14488A970` |
| Native add target in inspected controller vtables | `0x143564E20` | `0x143563AB0` |
| Accumulator double | receiver `+0x530` | receiver `+0x528` |

The native stick path uses both latest-axis fields for response, curve/configuration reads, and retained response interpolation. For X, `0x14489D353/+D35B` read Y/X; `0x14489D7BF–0x14489D812` includes response-factor interpolation; `0x14489D8BC` multiplies the result by a world-associated float at `+0x6E4`. **Inference:** this last float has the time-step role in stick rate-to-angle conversion; its field name is not recovered here. Mouse scaling follows a separate path with different configuration offsets and no corresponding final time-step multiply. Preserve both actual branches rather than substituting a guessed formula.

Output arguments are RCX=receiver and XMM1.low float. Native add targets retain ignore-input gating and optional legacy scaling before converting to double and accumulating: yaw `0x143564E96/+E9E`; pitch `0x143563B26/+B2E`. Use these native output calls so those gates/scales continue to apply.

The handlers are not pure numerical functions. An early mode branch bypasses the normal source selection (X `0x14489D262–0x14489D28F`). The common nonzero tail can call **`0x144898A70`** (X `0x14489DB5C`), which tests/clears `H+0xDAA` and performs additional callback/timer-like work. **Inference:** replaying an entire binding or all handler side effects twice is not automatically equivalent to emitting two angular contributions. The tail is guarded in the inspected path, but this is not a blanket proof of idempotence or reentrancy safety.

**Inference — architectural consequences**

1. The mouse and stick values have already undergone different processing before the magnitude comparison. Native angular scaling differs again afterward. A raw sum followed by one selected camera branch cannot preserve both source responses.
2. Changing `A+0x51` to additive, changing the global max loop, or changing only getter priority does not meet the requested behavior. The first two alter aggregation semantics; the third still discards a value.
3. A winner-only recorder cannot recover a loser. Recording at `0x14393475C` retains native mapping processing, including zero results, without running modifiers twice.
4. Empty camera action-modifier arrays make the narrow side-table design substantially smaller. If a camera configuration adds action modifiers/triggers, its complete processing/state contract must be checked; a second call through the same stateful object does not create an independent source history.
5. Manual cross-axis noninterference establishes the observed competition axes. It does not erase the static stick branch's cross-axis reads; those must remain stick-source reads in an additive design.

**Proposed — smallest camera-only architecture for the observed configuration**

Use a **generation-scoped camera contribution table**, then adapt only the recognized X/Y native camera calls. Keep the engine's original action evaluation and binding dispatch intact. The proposed composition occurs only in the native camera path.

| Piece | Proposed responsibility | Concrete boundary |
|---|---|---|
| Candidate retention | After the original mapping-modifier call returns, retain that mapping's processed typed value, physical identity, mapping identity, action/instance and evaluation identity. Capture zero explicitly. | Existing five-byte CALL `0x143934757`, with an ABI-correct return observer, or equivalent observer at `0x14393475C` |
| Camera eligibility | Recognized camera action/binding + corresponding MouseX/RightX or MouseY/RightY; supported scalar type/policy; complete current generation; known modifier/trigger contract | Existing generation/dispatch identities plus mapping and action array headers |
| Two source values per action | Maintain independent mouse and stick aggregates. If multiple supported mappings feed one source, retain original per-source max/tie ordering; never multiply output by the number of mapping records. | Side table; no writes to the stock merged value or movement records |
| Native camera fan-out | At a recognized ordinary camera value call, replace the one merged camera invocation with the eligible mouse and stick invocations, each with its own retained value. Do not emit the original merged value as a third contribution. | X CALL `0x144641BC8`, Y CALL `0x144640A18`, subject to reflected-path/activation validation |
| Branch identity | Supply a nested **camera subcall** source context to the existing camera getter wrappers; restore it on exit. Do not falsify the winner table or global CommonInput. | Existing X/Y getter redirects; movement getter logic continues reading original dispatch provenance |
| Source-specific latest samples | During native stick processing, both latest X/Y reads must refer to stick samples. During mouse processing, its writes must not become the next stick call's samples. Retain native stick response factors across evaluations. | Source-specific latest-axis storage and bounded save/select/commit/restore around eligible native calls, or equivalently redirected camera-only field accesses |
| Releases / inactive source | A zero, skipped, disabled or removed source must cease contributing; distinguish an observed zero from missing/invalid evidence. Mirror source release into its latest-axis state even while the other source keeps the logical action active. | Generation reset, mapping eligibility, native value/clear scheduling; clear sites already identified above |
| Final composition | Let the two native branches call the same existing yaw/pitch add target in the same consumption interval. | Existing virtual output calls and accumulators; no control/view modification |

The table key must include **owner, evaluation frame/generation, action and instance**; persistent response/latest-state ownership also needs the actual camera receiver and lifecycle identity. Do not key only by physical axis, globally cache one device, retain frame-local stack pointers, or reuse stale object identities after controller/context changes. Existing generation invalidation can be reused, but persistent response state must not be zeroed every evaluation.

The native binding should still execute once. Adapting its camera CALL is narrower than replaying `binding.vtable[1]`, which also carries action/timing/event behavior and may execute arbitrary reflected code. A camera CALL adapter must honor whether the original binding actually delivered an active value: `0x14392D940`'s zero-value path makes unconditional resurrection of retained candidates incorrect.

The intended numerical relationship is:

```text
mapped_mouse = original_mouse_mapping_processing(mouse_input)
mapped_stick = original_stick_mapping_processing(stick_input)

mouse_angle = original_mouse_camera_branch(mapped_mouse, native settings/state)
stick_angle = original_stick_camera_branch(mapped_stick, stick X/Y state, native settings/time)

camera accumulator receives mouse_angle and stick_angle through its existing add calls
```

For the observed empty action-modifier configuration, no extra action-modifier evaluation is needed. That is an evidence-based narrow eligibility condition, not permission to omit a nonempty chain. Similarly, preserve the original within-source axis dispatch/clear order; preloading both axes with future/current-frame values can change native response timing. A source-specific latest-sample bank must model that order, not silently substitute a new simultaneous-vector algorithm.

This is a **three-boundary design** (retention, eligible camera delivery/state selection, native additive output), not a claim that exactly three binary patches suffice. Clear handling, ordinary-mode gating, and common-tail side-effect handling may require additional narrowly scoped camera adapters. Entry-only two-call replay without those provisions is not the proposed finished implementation.

**Proposed — extension only if the narrow eligibility conditions fail**

Keep separate source action evaluations: mapping candidates → source-owned action value/modifier objects/trigger history → eligible source dispatch → native camera branch → common angular accumulator. Native camera-only action splitting or independently constructed shadow action state are possible realizations. A shallow copy of `I` or two calls using the same mutable modifier/trigger objects is insufficient. Mapping context priority, consumption, chords, pause behavior and rebinding must remain attached to their original mappings.

That larger option preserves native action processing where it actually exists, but needs action creation/lifetime/binding work that the current empty action-modifier observations do not justify as the first design. Neither option changes movement max/tie behavior, digital/left-stick classification, directional caches, or movement getter semantics.

**Inference / Proposed — remaining implementation questions, not a new bug-diagnosis campaign**

- **Trigger/activation contract:** mapping/action trigger counts and active objects were not captured by the existing camera observer. Confirm empty/simple camera triggers, or account for source-specific gating before allowing fan-out. Candidate magnitude alone is not trigger permission.
- **Delivery identity and multiplicity:** verify the targeted native wrapper is the relevant active-value path and establish exactly-once delivery per intended camera binding/receiver/source. Do not globally deduplicate actions in a way that suppresses legitimate distinct bindings.
- **State and release contract:** retain stick response factors, keep mouse samples out of stick X/Y reads, and define release/context-removal handling and native call order. The early alternate-mode path and shared tail must either retain their original single-call semantics or have a separately justified composition rule.
- **Supported configuration:** revalidate empty action modifiers at runtime; otherwise use stock behavior until independent action processing exists. The seven archived trials do not certify every game mode or later mapping rebuild.

These are bounded design details for a future implementation. The static map already identifies the separate source contributions and the native processing/composition boundaries. No movement or camera implementation has been changed in this pass.
