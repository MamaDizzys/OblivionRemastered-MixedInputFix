#pragma once

// Reset-mode cumulative stages: 0 validation only; 1 reset CALL; 2 winner;
// 3 dispatch; 4 camera and movement getters (production). Original movement
// branches stay intact. Explicit historical direct/trace modes retain their NOPs.
// Override with tools/build_local.py --stage N or a compiler definition.
#ifndef MIXED_INPUT_FIX_DIAGNOSTIC_STAGE
#define MIXED_INPUT_FIX_DIAGNOSTIC_STAGE 4
#endif
static_assert(MIXED_INPUT_FIX_DIAGNOSTIC_STAGE >= 0 && MIXED_INPUT_FIX_DIAGNOSTIC_STAGE <= 4,
              "MixedInputFix diagnostic stage must be 0 through 4");

// Mode 0 = production reset CALL/generation; Stage 1-only historical
// diagnostics: 1 = direct entry trampoline, 2 = five-argument scope-free trace.
#ifndef MIXED_INPUT_FIX_EVALUATION_MODE
#define MIXED_INPUT_FIX_EVALUATION_MODE 0
#endif
static_assert(MIXED_INPUT_FIX_EVALUATION_MODE >= 0 && MIXED_INPUT_FIX_EVALUATION_MODE <= 2);
static_assert(MIXED_INPUT_FIX_EVALUATION_MODE == 0 || MIXED_INPUT_FIX_DIAGNOSTIC_STAGE == 1,
              "Direct/trace evaluation variants require Stage 1");

namespace mixed_input
{
inline constexpr unsigned diagnostic_stage = MIXED_INPUT_FIX_DIAGNOSTIC_STAGE;
enum class EvaluationMode { Reset, Direct, Trace };
inline constexpr auto diagnostic_evaluation_mode = static_cast<EvaluationMode>(MIXED_INPUT_FIX_EVALUATION_MODE);
}
