# Additional camera keys: investigation and proposed inventory rule

No inventory predicate, composition code, DLL, or installed file was changed by
this investigation. The read-only live probe succeeded on Windows PID 340
(Linux PID 83238), confirming both key names and the Y modifier. The snapshot
passed its reread check and used 26,476 bytes of process-memory reads.
Evidence: live snapshot (`../../build/camera-prototype/key-investigation/live-keys-340.json`).

## Key identities and evidence

| Live FName | Confirmed live name | EKeys global RVA | Physical input |
| --- | --- | --- | --- |
| `0xCCA` | `NumPadSix` | `0x9113950` | Keyboard numpad 6 |
| `0xCD7` | `NumPadEight` | `0x9113980` | Keyboard numpad 8 |

These names were read directly from the current live FName pool and their
cached FKeyDetails independently reported digital type 0. This confirms the
earlier static reconstruction. The matching executable has
SHA-256 `b7be7e6ebe9424f6fdf274f5e7a59372de103e043ab5b66c60e021c0c89df457`.

The FKey initializers at `0x140901D28` and `0x140901BA8` call the ANSI FName
constructor with the strings `NumPadSix` and `NumPadEight` and the globals above.
The shipping name resolver at `0x140F56E50` establishes the two-byte entry
alignment, two-byte header, length at `header >> 6`, wide flag at bit 0, and
name-pool blocks at `0x14906C780 + 0x10`.

Walking the declared EKeys in global order from the observed `MouseX=0xBB9`
reproduces `MouseY=0xBBD`, `NumPadSix=0xCCA`, `NumPadEight=0xCD7`,
`Gamepad_RightX=0xE07`, and `Gamepad_RightY=0xE0F`. The one non-interning slot
at `0x149113EA8` is explicitly verified as a copy of the Delete FKey. This
reconstruction assumes the intervening names were interned consecutively; all
provided independent anchors agree. Numeric FName IDs must not become guards.

Independent physical-input evidence:

- `0x141137089` associates the NumPadSix string with Windows key code `0x66`;
  `0x1411370D9` associates NumPadEight with `0x68`.
- The registration blocks around `0x1411419E8` and `0x141141D84` use these FKey
  globals and pass key flags zero to the FKeyDetails constructor. The verified
  type encoding at `0x141134A64` gives digital type 0 for these flags.

These are ordinary additional digital bindings, not synthetic/composite analog
keys. The live journal establishes that they belong to the active X/Y action
objects, and the directional layout of numpad 6/8 is consistent with keyboard
turn/look controls. The particular asset/context that supplied those defaults
or rebindings has not been recovered. The current complete same-action lists are:

| Action | Index | Key | Modifier classes in execution order |
| --- | --- | --- | --- |
| `IA_Game_Movement_Turn` (X) | 71 | MouseX | Scalar, Scalar |
| same | 72 | Gamepad_RightX | DeadZone |
| same | 73 | NumPadSix | none |
| same | 74 | NumPadFour (`0xCBE`, digital 0) | Negate |
| `IA_Game_Movement_LookUp` (Y) | 68 | MouseY | Scalar, Negate, Scalar |
| same | 69 | Gamepad_RightY | DeadZone |
| same | 70 | NumPadEight | Negate |

All seven have zero mapping triggers. Mouse/stick keys report physical type 2
(1D); the three numpad keys report type 0. No NumPadTwo mapping exists for this
Y action in this snapshot. Scalar and DeadZone classes were identified, but
their parameter fields were not read. All mapping flags were zero at capture;
the earlier X rejection's flag 128 is therefore not a permanent key category.

The existing classifier recognizes only MouseX/Y and Gamepad_RightX/Y. Thus a
legitimate keyboard alternative returns Unknown and fails the axis guard before
inventory reaches its candidate scan. Neither rejected mapping had a candidate
in the recorded generation (`candidate_index=-1`); `candidate_count=10` is the
whole table, not ten candidates for either rejected mapping. Flags `128`/`0`
alone are not an inactivity or exclusion rule.

## The Y modifier

The earlier `0x17723CA60` was the modifier **array data pointer**, not the
modifier object. Addresses changed in the new process. The NumPadEight mapping
now resolves to object `0x11CE808B0`, named `InputModifierNegate_4`, class
`InputModifierNegate`. Its vtable is `0x1478420D8`, slot `+0x2B8` resolves to
`0x143933800`, and the three instance flags at `+0x28/+0x29/+0x2A` are all true.
Object-table, class, native-target, and reread checks passed. NumPadFour's
Negate modifier and MouseY's Negate modifier also have all three flags true.

Static inspection explains the confirmed modifier without invoking it:

- Native `InputModifierNegate` registration at `0x143919930` declares size `0x30`.
- Its constructor at `0x143922200` sets vtable `0x1478420D8` and three bools at
  `+0x28/+0x29/+0x2A` (defaults all true).
- Vtable slot `+0x2B8` points to `ModifyRaw` at `0x143933800`, which independently
  multiplies the three value components by ±1 according to those bools.

For a scalar action, the value is in component **0/X**, even when the camera
handler represents vertical/Y movement. Its enabled X flag negates the scalar
component: a +1 digital input becomes -1 through this modifier. This describes
the verified native implementation and instance settings, not an observed
keypress/output trace. The external probe
reads only those three bytes when both the exact native vtable/method and class
name match. Other modifier classes are identified but their fields remain
undecoded until their layouts are established.

## Smallest proposed behavioral change (not implemented)

Distinguish an inactive extra digital binding from an eligible composition source.
Keep composition limited to the existing per-axis Mouse/Gamepad pair.

1. Continue validating every same-action mapping's readable structural fields,
   empty trigger array, modifier-count bounds, key identity, and layout hash.
   Keep the extra mappings in the fingerprint; do not drop them from inventory.
2. Keep existing MouseX/Y and RightX/Y classification and wrong-axis rejection.
3. For an otherwise unrecognized key, require cached FKeyDetails whose embedded
   full identity equals the mapping key and whose physical type is **digital 0**.
   Null/unreadable/mismatched details, button-axis, other analog, and composite
   keys still reject. This is a positive type check, not `Unknown => ignore`.
4. Permit that digital mapping to contribute nothing **only when no matching
   `(action, mapping)` candidate exists in the current complete generation**.
   Any observed candidate, including zero or invalid candidates, forces native
   fallback. Do not retag digital as Mouse or feed it into either source sum.
5. Retain the existing `table.bad`, generation/owner/frame, orphan/alignment,
   duplicate, winner/value agreement, action-modifier/trigger, and native-mode
   checks. A digital winner or a participating digital mapping that loses the
   winner comparison still prevents composition.

Why absence can be the narrow criterion: in the inspected physical-mapping
routine, the modifier callback at `0x143934757` precedes the winner store at
`0x143934891`. The early inactive exit at `0x143934695` bypasses both. Existing
prototype capture retains unknown candidates as invalid records; it does not
silently discard them. The proposed rule depends on that coverage and the
existing supported, non-additive action contract. It does not infer zero merely
because the journal suppressed repeated rejections, or because a current
external snapshot shows an idle key.

This permits idle keyboard alternatives while preserving their normal native
behavior whenever they participate. A release may conservatively produce a
fallback generation too. A narrower first implementation could limit the
positive digital check to runtime identities of the confirmed directional
numpad globals, but fixed live IDs, mapping indices, names alone, flags, and
blanket unknown-key skips are inappropriate acceptance rules.

The live names/types, Y modifier, and complete same-action mapping lists are now
confirmed. Before accepting a behavioral implementation, test idle extra digital
keys, pressed/held/released numpad keys,
digital losing to mouse/stick, unknown analog/composite keys, unreadable details,
and rebinding/layout changes. Mouse/stick native output pairs must stay identical.

## Repeating the read-only capture

Use the existing diagnostic DLL. Start a fresh game process, exercise both camera
axes so that its current journal has the mapping evidence, and keep the game
running in ordinary stable gameplay. Use a journal from that launch, not the
now-exited PID 368 launch. Then run on the Linux host with process-read access:

```bash
python3 tools/camera_key_probe.py /path/to/current/main.dll.camera-PID.bin \
  --output build/camera-prototype/key-investigation/live-keys.json
```

`--pid` can select a **Linux** PID if needed; it is not the Windows journal PID.
The output path must be new. The reader opens `/proc/PID/mem` with `O_RDONLY`,
validates the executable hash and layout bytes, checks the current array against
the journal, validates UObject table entries, and rereads sampled bytes for
changes. It does not suspend the game, inject code, invoke UE functions, resolve
uncached FKeyDetails, or write game memory. Total memory reads are bounded to
1 MiB; each action is limited to 16 mapping rows and each row to four modifiers.
A stale pointer, failed read, exceeded bound, or changing snapshot stops output.

Preserve `live-keys.json` alongside the current journal. The snapshot is not synchronized to an evaluation
and cannot itself prove candidate inactivity. Seven synthetic reader tests pass;
the static reconstruction checks also pass against the exact executable and
the supplied live journal. The live probe passed on PID 340. Its success confirms
names, mapping membership, modifier identity/settings, and sampled coherence;
it does not establish same-generation candidate inactivity or authorize ignoring
an active keyboard mapping. The proposed inventory change remains unimplemented.
