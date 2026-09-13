# Mixed Input Logic Fix (MILF) for Oblivion Remastered

**Mixed Input Logic Fix (MILF)** fixes simultaneous native controller and real
mouse input in **The Elder Scrolls IV: Oblivion Remastered**.

The main reason I made it was to use **Steam Input gyro as an actual mouse**
without giving up native controller input. Oblivion Remastered technically
accepts both input methods at once, but parts of its input handling can start
fighting themselves when they are used simultaneously.

The goal is simple: mouse input should behave like mouse input, controller input
should behave like controller input, and neither should break the other.

## What It Fixes

Mixed Input Logic Fix is designed to preserve all of these at the same time:

- true analog left-stick movement
- native controller buttons and triggers
- native right-stick camera control
- real mouse camera input
- Steam Input gyro configured as mouse

This is not a mouse-to-joystick conversion. Gyro can remain real mouse input.

MILF also does not impose a blanket "mouse wins" or "controller wins" rule.
Instead, it preserves the game's native input semantics as closely as possible.

For movement, the game's existing Enhanced Input arbitration still decides
which mapping wins an action. MILF tracks the physical source of that winner so
the game interprets its value correctly.

For camera input, mouse and right-stick contributions need to remain distinct
long enough to pass through their own native camera paths instead of one source
being discarded before camera processing.

## Current Status

**v1.0.0 — Live Verified**

Both movement and camera mixed-input behavior have been validated in-game.

### Movement

- W/S/A/D work normally.
- Analog magnitude and diagonals are preserved.
- Native left-stick movement continues working during continuous real
  mouse/gyro input.
- Mixed keyboard and controller movement follows the game's existing
  magnitude-based arbitration.
- Fractional analog input correctly loses to a full digital `1.0` input.
- Full-strength analog input can win an exact-magnitude tie according to the
  game's normal mapping order.

### Camera

- Real mouse input works normally by itself.
- Native right-stick camera input works normally by itself.
- Mouse and right-stick input on the same axis can contribute at the same time.
- Same-direction input combines instead of one source suppressing the other.
- Opposing input naturally dampens rather than producing the previous hard
  winner-takes-all behavior.
- Horizontal and vertical camera axes have both been live-validated.
- Digital keyboard camera bindings retain the game's original fallback
  behavior.

The v1.0.0 production candidate has passed the full static regression suite and
final live-game smoke testing.

One native game limitation remains intentionally unchanged: combining digital
camera-turn bindings such as NumPad camera keys with the native right stick can
produce competing or stuttering movement. The same behavior occurs with MILF
disabled, so v1.0.0 preserves it rather than inventing new digital-plus-analog
camera semantics.

## Why The Bug Happens

Oblivion Remastered does support mouse and controller input at the same time, but
two different parts of its input pipeline make assumptions that break under
simultaneous use.

### Movement

The game keeps a global current-input-type state through CommonInput. During
mixed input, that global state can disagree with the physical source of the
movement action currently being processed.

That matters because digital movement and analog stick movement use different
native value semantics.

MILF tracks which physical mapping actually won the existing Enhanced Input
arbitration for each movement action:

- a verified digital winner uses the native digital movement path
- a verified left-stick winner uses the native signed analog path
- anything unknown or unsupported falls back to the original CommonInput
  behavior

The original movement branches, mapping order, modifiers and global input-type
state are otherwise left intact.

### Camera

The camera problem happens earlier.

Mouse and native right-stick mappings for the same camera axis enter Enhanced
Input as separate candidates, but the game reduces them to a single
maximum-magnitude winner before native camera processing.

That means the weaker source can disappear completely. The camera handler never
gets a chance to combine mouse and stick input because only one of them reaches
it.

The camera fix retains the relevant mouse and stick candidates before that
collapse, passes each through its own native camera path, and lets the existing
camera accumulator combine the resulting angular contributions.

Digital keyboard camera bindings remain separate from this composition logic and
fall back to native behavior whenever they participate.

## Requirements

- **The Elder Scrolls IV: Oblivion Remastered**
- **UE4SS**

The mod validates the expected game code before installing its patches. If the
relevant executable signatures do not match, it fails rather than blindly
patching unknown code.

## Installation

1. Install **UE4SS** for Oblivion Remastered.
2. Download the MILF release archive.
3. Extract it into:

   `OblivionRemastered/Binaries/Win64/`

The archive is already laid out to merge with the existing `ue4ss` folder.

After installation, the mod should be located at:

`OblivionRemastered/Binaries/Win64/ue4ss/mods/MixedInputFix/`

with:

    MixedInputFix/
    ├── enabled.txt
    └── dlls/
        └── main.dll

To uninstall, remove the `MixedInputFix` folder from `ue4ss/mods/`.

## Documentation

The project documentation is split into three areas:

- [`docs/reference/`](docs/reference/) — reverse-engineered behavior, hook sites,
  calling contracts, implementation details and evidence.
- [`docs/guides/`](docs/guides/) — capture, diagnostic and reproduction procedures
  used during development and validation.
- [`docs/addendums/`](docs/addendums/) — historical notes, dead ends and the
  development story.

For the full chronological reverse-engineering record, see
[Development History](docs/addendums/development-history.md).

Some documents preserve superseded prototypes or investigative procedures for
reference. The README and current source should be treated as the authoritative
description of the current implementation.

## Source Layout

- `src/` — mod implementation
- `tests/` — standalone and integration test sources
- `tools/` — build, validation and live-capture tooling
- `docs/reference/` — formal reverse-engineering reference
- `docs/guides/` — reproduction and debugging procedures
- `docs/addendums/` — informal and historical documentation

## Building

The build helper reuses headers, defines and libraries from an existing
configured UE4SS build tree.

A production build can be created with:

    python3 tools/build_local.py --stage 4 --ue4ss-root /path/to/UE4SS

If `--ue4ss-root` is omitted, the helper uses the development-tree layout it was
originally built against.

Additional flags are available for standalone tests, diagnostics and experimental
camera builds:

    python3 tools/build_local.py --help

Build products are written to `build/` and are not tracked by Git. Experimental
and diagnostic DLLs use separate filenames so they do not overwrite the
production candidate.

## Project Scope

Mixed Input Logic Fix is deliberately narrow.

It is meant to correct Oblivion Remastered's mixed-input behavior while
preserving as much of the game's native input pipeline and device-specific
semantics as possible.

It is not intended to replace Enhanced Input, globally prioritize one device,
or turn mouse input into controller input.

## License

Mixed Input Logic Fix is licensed under the
**GNU General Public License v3.0 only (`GPL-3.0-only`)**.

The source can be studied, modified and redistributed under the terms of the
GPLv3. Distributed derivative works must remain available under the same
license.
