# Camera prototype inventory diagnostic

The first live prototype journal reports `mappings`, so composition was never
reached for that recorded dispatch. The old journal suppresses later occurrences
of the same reason across both axes. In `Provenance.hpp`, axis **1 is X** and
axis **2 is Y**; that one row cannot establish the other axis's behavior.

The diagnostic preserves the existing inventory predicates, their order, layout
hash, composition, and native fallback. It changes only the prototype header,
journal reader, and tests. Production source and artifacts are not rebuilt.

Journal version 2 appends a 160-byte inventory payload to each 144-byte record.
The 4,096-slot journal remains bounded (1,245,248 bytes including its header).
Mapping failures are suppressed separately per `(axis, subreason)` for the
process lifetime: at most 50 mapping rejection records. Other rejection reasons
retain their previous suppression. The analyzer accepts both journal versions.

Every `inventory()` failure now identifies its first failing predicate:

- Mapping-array pointer/count reads, null pointer, negative count, or count over 1,024.
- Action read; classified axis mismatch; unknown source; trigger-count read or
  nonzero count; key/modifier-pointer/modifier-count/flag read; modifier count
  below zero or above 64.
- Observed candidate invalidity, instance mismatch, axis mismatch, or source mismatch.
- Final candidate scan: invalid candidate, pointer before/after the array, or
  pointer misaligned to the assumed 0x50-byte mapping stride.
- No mapping for the dispatched action.

The payload includes the owner array address/count; mapping address/index/action;
raw eight-byte key and four camera EKeys identities; classification; trigger and
modifier counts/pointer; flags; candidate count/index/mapping/action/instance and
validity/source/axis; and the layout hash accumulated **up to rejection**. The
record also retains dispatch generation/frame/owner/action/instance/receiver,
axis, and thread. It does not dump arbitrary game memory or resolve key names.

Read-success bits distinguish unavailable fields from readable zeroes. Values
already read by guards are retained; missing context is sampled with guarded
reads after failure. Those samples do not influence eligibility and are not an
atomic memory snapshot. A failed guard may therefore coexist with a successful
later sample; the subreason remains the authoritative failing predicate.
Source fields are zero if classification was not reached. Candidate fields are
null in the summary when no matching candidate was observed. The partial hash
is not proof that the entire inventory was validated.

The axis guard deliberately precedes the unknown-source guard, as before. An
unrecognized key therefore normally reports `source_axis` with source/axis
`Unknown`. Compare its raw key against the four EKeys values before interpreting
that as a mapping to the other camera axis. `candidate_invalid` identifies the
failed inventory predicate; it does not yet distinguish the upstream checks that
set `Candidate::valid` in `modify()`.

## Synthetic verification

```bash
python3 tools/build_local.py --ue4ss-root /path/to/UE4SS --camera-prototype-tests
WINEPREFIX=/path/to/mixed-input-fix-wine WINEDEBUG=-all wine build/camera-prototype-tests.exe
python3 tests/camera_prototype_journal.py
python3 tools/build_local.py --ue4ss-root /path/to/UE4SS --camera-prototype
```

The fixture journal uses `CREATE_NEW`; archive any previous test journal with
the same process ID before rerunning. The suite retains the shipping handler,
modifier, native-add, cleanup, and patch-restoration checks. Added cases exercise
granular rejection predicates, unreadable memory, payload values, suppression
across repeated X/Y failures, distinct predicates on the same axis, and native
winner fallback. Python tests cover both layouts, missing reads, uncommitted
records, saturation, and malformed files.

## Evidence needed from the next live run

No diagnostic installation is performed by this task. Before a later live run,
record the diagnostic DLL's SHA-256 so its journal is tied to the tested artifact.
Keep the same game build, bindings, save, and settings as the first run where
practical; note any differences.

In ordinary unpaused gameplay, briefly exercise horizontal and vertical mouse
movement, horizontal and vertical right stick, then simultaneous mouse/stick
movement on both axes. Exit normally to obtain a complete file. Return:

1. The new `main.dll.camera-<pid>.bin` and its complete summary from
   `python3 tools/analyze_camera_prototype.py <journal>`.
2. The loaded DLL hash and load log, plus a short confirmation of the inputs
   exercised, stability, and whether mixed camera behavior remained vanilla.
3. All `first_rejections`, including the per-axis inventory payloads. Do not
   extract just the first `mappings` row. Keep `records`, `claimed`, `saturated`,
   and `verified_pairs` so incomplete evidence is visible.

The decision point is the first failing predicate and its matching mapping/key,
counts, and candidate context for each exercised axis. Missing rejection records
are not proof of success. No guard should be changed until this evidence explains
why the live inventory differs from the synthetic fixture.
