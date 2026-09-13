2026-09-07 movement update: the reset CALL / generation / synchronous-dispatch calling contract below is retained. Production replaces the four NOPs with four five-byte movement getter CALL redirects and leaves the original `75 0F` branches intact. Two added leaf adapters at near-page +0xC00/+0xE00 tail-jump to ordinary one-object Windows x64 getter wrappers; they preserve the original +5 return address. The reset shim occupies +0xB00 through +0xB8A including its inline target, so the new adapters do not overlap it or unwind/slot storage. No evaluation scope or entry detour was reintroduced. Final DLL audit and test status: movement audit (`build/movement-production/audit.txt`); implementation and Live Verified / Static Analysis / Inference distinctions: [movement review](movement-and-camera.md). The final v1.0.0 production candidate has now been live-validated for movement and mixed camera input. The baseline live campaign also confirms the physical caller, saved evaluation frame and synchronous movement dispatch chain in its sampled windows. Camera composition is no longer deferred; the final implementation is documented in [movement-and-camera.md](movement-and-camera.md).

The following is the historical calling-contract review; its old movement-NOP patch inventory and live-status statements are superseded.

---

Extended live update, 2026-09-06: the user has successfully validated production startup, native analog movement with mouse/gyro, both camera sources independently, freestanding/swimming/horseback gameplay, menus, and save swapping. The reset/generation architecture remains the working production baseline. Keyboard Backward/Left fail under the four unconditional movement NOPs, and simultaneous opposing camera inputs can stall the conflicting axis. See [MOVEMENT_CAMERA_REVIEW.md](movement-and-camera.md) for the branch diagnosis, proposed replacement, and observing capture plan. The old recommendation below to keep the four movement patches is superseded as a future-fix requirement; the current candidate is preserved unchanged during diagnosis. Nothing was automatically installed.

The implementation and calling-contract report below is preserved history; its outstanding production startup/gameplay checks are superseded by the live results above.

Production implementation update, 2026-09-06: **reset-CALL/generation candidate built and tested; not installed by Codex**.

The user live-confirmed that the corrected five-argument trace reaches the main menu and emits both first-execution and first-normal-return markers. The missing fifth work-list argument is therefore confirmed as the cause of the prior four-argument trace startup crash. This does not validate the old evaluation-wide scoped wrapper as a production design; it has now been removed.

The design below is implemented. Production leaves entry RVA `0x392B630` untouched and changes only the destination of the existing five-byte reset CALL at `0x392B6A6`. The near shim preserves incoming machine state and tail-jumps to `0x3939FA0`, retaining the original return to `0x392B6AB`. Winner and dispatch keep their six-byte indirect CALLs; both camera comparisons and four movement NOPs retain their prior behavior. All 15 existing signatures remain, plus a new owner-setup signature at `0x392B650`; all 16 match the shipping image. Transactional writes/restoration, rejection of changed bytes, thread suspension checks and pinned callback storage remain intact.

The additional frame evidence needed for implementation is bounded to the already inspected prologues:

| Identity | Derivation |
|---|---|
| Reset evaluation frame | Evaluation entry S; RBP=S−0x538; reset CALL entry T=S−0x640; therefore **RBP=T+0x108** |
| Winner's caller frame | Mapping entry M; mapping RBP=M−0x3F; initial PUSH RBP saves caller at M−8; therefore **saved evaluation RBP is mapping `[rbp+0x37]`** |
| Dispatch evaluation frame | Existing synchronous dispatch site still has evaluation RBP and owner R13; adapter forwards them in R9/R8 |

Reset bookkeeping validates that frame/RSP relationship. Winner recording guardedly reads the saved frame and validates owner/frame before capturing the current generation; record and lookup operations verify that generation token. This prevents resumed outer work from populating a nested evaluation's table. Foreign/unknown mappings erase known winners; owner/frame mismatches invalidate the table. The table is persistent `constinit` TLS with no stack-local evaluation pointer or evaluation-exit cleanup. Reset advances generation and clears count in constant time; overflow/invalid identity disables overrides. Counter exhaustion permanently disables that thread instead of wrapping into an old token.

Only synchronous dispatch is scoped, with C++/SEH restoration retained. Unknown/mismatched dispatch masks outer state. Getters validate current generation/frame, action/instance and policy/axis, and reject a snapshot if its record was replaced or invalidated. A nested reset invalidates old dispatch tokens immediately; after inner work returns, outer provenance is not restored. Outside dispatch all getters use vanilla CommonInput. No evaluation return thunk or return-address write was added.

The actual reset shim has 131 code bytes plus an eight-byte original-target pointer. It pushes flags and allocates 0x260 bytes, preserving volatile GPRs and a 16-aligned FXSAVE64 image for x87/XMM0–15/MXCSR. All writes and helper home space are below incoming RSP. It clears DF before the helper, restores FX/GPR state and flags/RSP, then tail-jumps indirectly without clobbering a register. Three dynamic unwind entries cover body/prologue, POPFQ, and tail jump. Final DLL audit identifies the 158-byte bookkeeping helper at RVA `0x6F80`: scalar native TLS access, no calls, loops, dynamic initializer, allocator, diagnostic or AVX instruction. AVX upper state is untouched by this particular emitter/helper build. Detailed audit and dumps are in `build/production-audit.txt`, `build/reset-shim-disassembly.txt`, and `build/reset-generation-linked-disassembly.txt`.

All tests passed: host provenance reset/rollover/nesting/stale/Unknown/masking/fallback; new Windows reset state comparison with stress clobbers, original-call count, every-instruction unwind, actual CALL install/in-flight restore, signature safe failure and recorder/dispatch/getter integration; existing Windows bridges including C++/SEH dispatch and six-byte in-flight restore; retained direct/five-argument trace regression. The trace fixture now executes the first 62 shipping bytes to retain the new owner signature, while preserving its previous forwarding checks. The prior evaluation-wide scope tests and artifacts are preserved in `build/five-argument-confirmed-checkpoint/`, not used as the production model.

Candidate: `build/MixedInputFix-production-candidate.dll`; SHA-256 `0a945b1ce600abe54de83bc1ba9f37df55149cbe051d97d109157f07bd95a053`. The live-confirmed trace and direct DLLs remain unchanged. Source defaults to Stage 4/reset; explicit Stage 1 direct/trace diagnostics remain available. Nothing installed into Oblivion.

Remaining live uncertainty: production startup and mitigation compatibility, winner saved-frame equality to the reset identity, vertical physical-key/synchronous-dispatch chain, and gameplay/menu/focus/reconnect scenarios. The new frame checks are statically derived and synthetically exercised, not yet live-confirmed. Nested evaluation fallback is intentionally conservative. No broader reverse-engineering survey was repeated.

The original confirmation and design reports follow as preserved history; their statements that the redesign is not implemented or the corrected trace is not live-tested are superseded above.

---

Five-argument confirmation update, 2026-09-06: **built and standalone-tested, not installed**. The original analysis/design report is retained below; its statements that prototypes are still four-argument and no confirmation DLL has been built are historical.

The user supplied live GDB evidence from the same evaluation invocation:

| Probe | Value |
|---|---|
| Caller VA `0x14383AEAC`, outgoing `[rsp+0x20]` | `0x1492801F8` |
| Evaluation VA `0x14392D294`, `[rbp+0x560]` | `0x1492801F8` |
| Header qword at `0x1492801F8` | `0x000000013E2BE480` |
| Header qword at `0x149280200` | `0x0000000400000000` |

The equality live-verifies argument-five forwarding. Header fields remain consistent with an array-like data pointer, Num=0 and Max=4; the exact engine type is still unknown. These observed addresses are evidence only. The four-argument trace's outgoing WriteFile null followed by no fifth-argument restoration is a proven ABI bug with a concrete explanation for the pre-menu crash. A captured live fault instruction is still absent.

The implemented diagnostic contract is `void (*)(void* owner, void* components, float delta, bool paused, void* work_list)` under the target's normal Windows x64 ABI. Both source wrappers and the trampoline type now agree; only the scope-free trace is selected for the new DLL. The preserved scoped wrapper received argument forwarding, not a lifetime/provenance redesign. No sixth input, non-void return requirement, or additional live calling requirement was established in this pass.

Generated-code proof in `build/evaluation-five-argument-audit.txt` and the adjacent object/linked-DLL disassemblies: PDB identifies evaluate_trace at DLL RVA `0x6120`, size 323. With S=trace entry RSP, the prologue makes W=S−0x88. At +0x11, `mov rbx,[rsp+0xB0]` reads S+0x28 before any I/O; Win32 calls preserve RBX. At +0xA7, **all paths** store RBX at outgoing W+0x20; +0xAC calls the trampoline pointer (linked slot RVA `0x11ED08`). Its pushed return address makes the slot callee-entry-RSP+0x28. Both diagnostics use W+0x20 for WriteFile argument five and W+0x34 for its written-count buffer, entirely below S. They never write the original incoming stack arguments. The return marker runs only after the game call returns. Targeted instruction bytes and the RIP-relative trampoline pointer destination were checked in the final linked DLL. LLVM's nearest-export labels in that dump are not function identities.

The focused standalone test now reads `[rbp+0x560]` after the exact first 32 shipping bytes and dereferences header offsets 0/8/12, using changing non-null pointers, including Num=0/Max=4. It preserves and checks the original caller's fifth/sixth slots after entry and return I/O, checks untouched provenance TLS and the Stage 1 patch subset. Repeated calls produced exactly one entry and one successful-return marker. Focused Windows, existing bridge Windows, and host provenance suites passed. The retained scoped tests were updated for the fifth pointer, retaining recursion and C++/SEH unwind checks. This does not prove live startup safety or full machine-state transparency.

Confirmation artifact: `build/MixedInputFix-stage1-trace.dll`; SHA-256 `a8ccce4816ea032e17b943158b680c68147f604188ee5c7c99a5edc7a536d836`. Four movement patches retained; winner, dispatch and getter hooks disabled. Prior trace artifacts/source/docs are checkpointed in `build/four-argument-trace-checkpoint/`. Direct DLL unchanged. Nothing installed into Oblivion.

The reset/generation architecture below is still recommended for production, even if the five-argument trace succeeds. Its reset-call boundary preserves the game's evaluation frame, avoids an evaluation lifetime wrapper and return-address substitution, and supports bounded nonthrowing bookkeeping with conservative generation/frame/owner gates and synchronous dispatch-only scopes. It has not been implemented in this confirmation pass.

---

Evaluation calling-contract review, 2026-09-06. Analysis/design only: no hook implementation, DLL rebuild, or live installation in this pass.

The live direct-trampoline variant reaches the main menu; the four-argument C++ trace variant enters and crashes before its return marker. The shipping code proves a missing fifth argument. A normal Windows x64 call boundary is not inherently incompatible with this function: the existing four-argument boundary omits a required input. The exact live fault instruction remains unconfirmed without a crash address.

All addresses below are RVAs. The inspected executable has SHA-256 `b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`. Local disassembly and survey outputs are in `build/calling-contract/`. Misleading nearest-export labels from LLVM are not used as function names.

## Proven call chain

The object constructor at `0x3923D20` calls the base constructor, then installs vtable `0x7846CA0` at `0x3923D37–0x3923D3E`. Its slot `+0x2E0`, at `0x7846F80`, contains `base+0x392B630`. The earlier slot `+0x2D0` contains `0x3934A10`, a five-byte tail jump to `0x383ADD0`. This distinguishes the outer four-argument input-stack routine from the five-argument evaluation function we patched.

| Site | Proven behavior |
|---|---|
| `0x358A747` | Calls the input object through vtable `+0x2D0`, supplying RCX, RDX, XMM2 and R9B. This is an upstream input-processing driver. |
| `0x3934A10` | Tail-jumps to `0x383ADD0`, preserving that outer call's arguments and stack. |
| `0x383AE91` | Inside `0x383ADD0`, calls preprocessing through vtable `+0x2D8`; R9 points to the shared work-list header at `base+0x92801F8`. |
| **`0x383AEAC`** | Calls evaluation through vtable `+0x2E0`, with the **same work-list pointer as argument five**. This is the concrete call site into `0x392B630` for the identified vtable. |
| `0x392D2BE` | Evaluation forwards all five argument positions to downstream processing at `0x3820180`. |

The decisive caller instructions are:

```asm
0383AE7D  lea   r15, [base+0x92801F8] ; RIP-relative in the actual encoding
; Preprocessing receives R15 in R9 and returns.
0383AE97  mov   rax, [rbx]
0383AE9A  movzx r9d, sil
0383AE9E  movaps xmm2, xmm6
0383AEA1  mov   [rsp+0x20], r15       ; fifth argument before CALL
0383AEA6  mov   rdx, rbp
0383AEA9  mov   rcx, rbx
0383AEAC  call  qword ptr [rax+0x2E0]
```

The outer caller later walks/releases this list's 32-byte elements and resets its count. The downstream consumer loads its data pointer at `+0` and count at `+8`. These establish an array-like work-list header; the exact C++ element type/typedef is not established. Its observed global address is evidence, not a proposed hardcoded replacement for argument forwarding.

## Actual machine-level inputs

Let `S` be RSP at entry to `0x392B630`, after the original CALL pushed its return address.

| Input | Location | Evidence |
|---|---|---|
| Input owner/object | RCX | Set from RBX at the caller, homed at `S+8`, retained in R13. |
| Component-stack header/reference | RDX | Set from the outer caller's RBP, homed at `S+0x10`, later dereferenced as an array header. |
| Scalar delta | XMM2 low 32 bits | Caller loads XMM2; evaluation saves it in XMM14 and uses single-precision arithmetic. |
| Pause flag | R9B | Caller zero-extends SIL; evaluation homes and reloads the byte. |
| **Work-list header/reference** | **`[S+0x28]`** | Caller explicitly writes its outgoing `[rsp+0x20]`; evaluation reads and forwards it. |

An ABI-level declaration needs **at least** `(void* owner, void* components, float delta, bool paused, void* work_list)`. The observed caller does not consume a return value, consistent with void. Opaque pointers here describe forwarding; they do not establish complete engine types.

The evaluation frame sets `RBP=S-0x538`. Consequently:

```asm
0392D294  mov   rax, [rbp+0x560] ; S+0x28: original fifth argument
0392D29B  movaps xmm2, xmm14
0392D29F  movzx r9d, byte ptr [rbp+0x558]
0392D2A7  mov   rcx, r13
0392D2AA  mov   rdx, [rbp+0x548]
0392D2B9  mov   [rsp+0x20], rax  ; fifth argument to downstream call
0392D2BE  call  0x3820180
```

Downstream processing sets its own `RBP=S2-0x4D8`, reads `[rbp+0x500]` (again entry-RSP+0x28) into RSI at `0x3820257`, then dereferences `[rsi]` and `[rsi+8]` at `0x38202B0/0x38202B3`. This path is taken when the component stack has a nonnegative last index and contains a non-null component. Passing null therefore has a concrete invalid-read path.

No sixth-or-later stack input was found in the evaluation body. Home slots are used conventionally: the function writes RCX/RDX/R9B itself and also reuses a home slot to save RSI. They are not evidence of additional arguments. No need for prefilled home-slot contents, an original-caller return-address check, or a special caller-frame identity was found in its argument handling.

No additional incoming volatile GPR/SIMD input was established. R8 is not the third argument here because that position is occupied by a floating-point argument in XMM2. The function saves the inputs it needs before nested calls; the early reset helper operates on RCX and is not an apparent channel for extra incoming registers. XMM14/XMM10 copies preserve full vectors, but the observed delta calculations and caller setup support scalar float semantics. There is no positive evidence for `__vectorcall` or a custom optimized convention. An eventual transparent shim should nevertheless preserve machine state, avoiding dependence on this negative finding.

## Why the current trace loses argument five

The compiled trace artifact is particularly revealing; see `build/evaluation-trace-disassembly.txt`:

```asm
evaluate_trace+0x71  mov qword ptr [rsp+0x20], 0 ; WriteFile argument 5: lpOverlapped
evaluate_trace+0x8C  call WriteFile
; OutputDebugStringA and SetLastError; restore four declared game arguments.
evaluate_trace+0xB3  call [evaluation_trampoline]
```

There is no work-list reload/store between these calls. On the logged first-entry path with an open diagnostic file, the trampoline receives null as its fifth argument. The original caller's valid work-list pointer remains higher in the wrapper's caller frame and is never forwarded. Later calls also lack defined fifth-argument forwarding. The scoped production wrapper has the same incomplete prototype.

This explains why direct execution can work while a logged C++ call fails before return. It is a proven ABI bug and a strong explanation of the live failure; it is not a captured crash stack. The prior standalone trace test explicitly guaranteed only four arguments and used a body that did not dereference argument five, so passing that test could not validate this live contract.

## Call-site survey limits

The executable-wide target scan found no direct rel32 CALL/JMP to `0x392B630`, no RIP-relative LEA materializing its address, and one absolute pointer to it: the identified vtable slot. I surveyed the executable's decoded references to displacement `0x2E0`, including REX/SIB forms, memory-indirect calls/tail jumps and loads followed by register calls. There were 928 decoded memory-indirect call/jump sites sharing that offset; most belong to unrelated vtables. Float-argument candidates, forwarding/tail cases and the input-processing neighborhood were inspected. `0x383AEAC` is the one concrete compatible evaluation caller identified, not 928 callers of this function.

Static displacement scanning cannot prove the receiver type of every unrelated indirect call, rule out arbitrarily transformed/cached function pointers, or enumerate code in external/live-injected modules. Thus this is a practical static call-site inventory, not a claim to have enumerated every possible runtime caller. The fifth-argument proof does not depend on completeness of that inventory.

## Recommended architecture

For a design that avoids calling evaluation through a C++ prototype, prefer **a transparent shim on the existing reset CALL plus persistent generation-tagged provenance and dispatch-only scopes**. Do not introduce an evaluation return thunk now.

1. The unconditional CALL at `0x392B6A6` already calls reset routine `0x3939FA0` and resumes at `0x392B6AB`. At this point the evaluation prologue is complete, R13 identifies the owner, RBP identifies its frame, and delta is preserved in XMM14. Replace only this CALL's destination with a near assembly shim. After bookkeeping, the shim tail-jumps to the original reset routine. The reset routine's original caller return address and evaluation frame stay intact. No call through an inferred evaluation prototype is involved, and the evaluation entry detour is unnecessary for this architecture.
2. The shim saves flags, volatile GPRs and SIMD state below the incoming RSP, reserves its own correctly aligned helper home space, and preserves MXCSR/other machine state the helper could change. It must not write the game's existing home area or stack arguments. Call only a known local bookkeeping helper; restore state/RSP exactly, then use a register-preserving tail jump. Keep dynamic unwind metadata correct for the temporary shim frame. Bookkeeping must be bounded, nonthrowing, allocation-free and free of game callbacks or runtime logging.
3. Bookkeeping resets a persistent per-thread table, advances a generation, and records owner plus evaluation-frame identity. There are no pointers to stack-local Evaluation objects. Do not save or substitute the original evaluation return address.
4. Recording and dispatch must validate owner **and evaluation frame/generation**, not merely owner. A later nested evaluation advances the generation; resumed outer recording must not populate the inner generation. The current recorder lacks the necessary frame-generation checks, so this cannot be implemented by merely making its existing Evaluation object persistent.
5. Scope only the synchronous dispatch call. Its stack-local context snapshots the winner and generation; every dispatch, including Unknown, masks an outer context. Getter overrides require a matching current generation/frame and dispatch identity. With no active dispatch, persistent records cannot affect getters.
6. Nested evaluation invalidates the older generation conservatively. Existing outer dispatches then fall back; resumed outer evaluations with mismatched frame identity also fall back until the next reset. This deliberately sacrifices provenance overrides for affected recursive work instead of attributing stale input. If full restoration of recursive outer provenance becomes required, a more complex bounded multi-frame design needs separate proof.

After normal or exceptional evaluation exit, retaining records is harmless **only under those gates**: no outside dispatch can consume them, and every subsequent evaluation resets first. Overflow, invalid frame identity and generation rollover must invalidate overrides. Normal return cleanup is unnecessary for the persistent table; C++/SEH cleanup remains confined to the already synchronous dispatch scope.

An entry shim can implement the same generation start while saving incoming state, doing minimal bookkeeping and tail-jumping to the existing trampoline. It must restore the original entry RSP and all stack inputs exactly. The reset CALL is preferable because it gives an established game frame and existing call boundary, and needs no evaluation-entry lifetime machinery.

A return-address substitution design would need per-thread/per-invocation original-return storage, recursion support, preservation of all return channels, and a solution for exceptions that bypass normal RET. Those burdens provide no benefit for the proposed persistent-generation design. Avoid it here.

The smallest separate confirmation experiment would be a five-argument trace wrapper that forwards the opaque work-list pointer and a test body that actually dereferences it. That is a diagnostic option, not an implementation made in this report. Keep all four movement patches in any future build; retain the production implementation until the chosen replacement is validated.
