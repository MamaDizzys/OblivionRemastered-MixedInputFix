**Mixed Input Logic Fix (MILF)** fixes simultaneous native controller and real mouse input in **The Elder Scrolls IV: Oblivion Remastered**.

The main reason I made it was to use **Steam Input gyro as an actual mouse** without giving up native controller input. This is not mouse-to-joystick emulation: mouse input remains mouse input, controller input remains controller input, and the mod tries to preserve the game's native behavior for both.

## What v1.0.0 fixes

- True analog left-stick movement can coexist with continuous real mouse/gyro input.
- Keyboard and controller movement retain the game's native magnitude-based arbitration.
- Native controller buttons and triggers remain controller input.
- Native right-stick camera control can coexist with real mouse camera input.
- Steam Input gyro can be configured as **Mouse** rather than Joystick.
- Unsupported or unrecognized input cases conservatively fall back to the game's original behavior.

## How it works

Oblivion Remastered has two separate mixed-input problems.

For movement, the game can interpret an action according to its global current-input-type state rather than the physical mapping that actually produced the winning value. MILF tracks that winning mapping and preserves the correct native digital or analog semantics.

For camera input, mouse and right-stick mappings on the same axis compete in Enhanced Input's magnitude-based winner arbitration. Normally, the weaker candidate can be discarded before native camera processing ever sees it. MILF preserves the relevant mouse and stick contributions long enough for each to pass through its own native camera path, then lets the game's existing camera accumulator combine the results.

Digital keyboard camera bindings remain separate and fall back to native behavior whenever they participate.

## Installation

Requires **UE4SS**.

Extract the release archive into:

`OblivionRemastered/Binaries/Win64/`

The archive is already structured to merge with the existing `ue4ss` directory.

The installed mod should end up at:

`OblivionRemastered/Binaries/Win64/ue4ss/mods/MixedInputFix/`

To uninstall, remove that `MixedInputFix` folder.

## Source and documentation

The repository includes the source, standalone/integration tests, reverse-engineering reference material, debugging tools, and the project's development history.

Licensed under **GPL-3.0-only**.
