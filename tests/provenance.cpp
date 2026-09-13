#include "../src/Provenance.hpp"
#include <cassert>
#include <thread>
#include <stdexcept>
#include <cstdio>
using namespace mixed_input;
int main()
{
    int owner{}, other_owner{}, action{}, instance{}, other_instance{};
    auto& e = provenance;
    constexpr std::uintptr_t outer_frame = 0x200000, inner_frame = 0x1F0000;
    assert(!e.valid && current_winner(Axis::X).source == Source::Unknown);
    e.reset(&owner, outer_frame);
    const auto outer = e.generation;
    assert(outer.number == 1 && e.valid);
    e.record(outer, &action, &instance, {Source::Mouse, Axis::X});
    assert(e.lookup(outer, &action, &instance).source == Source::Mouse);
    e.record(outer, &action, &instance, {Source::Gamepad, Axis::X});
    assert(e.lookup(outer, &action, &instance).source == Source::Gamepad);
    e.record(outer, &action, &instance, {});
    assert(e.lookup(outer, &action, &instance).source == Source::Unknown);
    e.record(outer, &action, &instance, {Source::Mouse, Axis::X});
    assert(e.lookup(outer, &action, &other_instance).source == Source::Unknown);
    assert(current_winner(Axis::X).source == Source::Unknown); // No dispatch.
    Dispatch active{outer, &action, &instance, e.lookup(outer, &action, &instance)};
    {
        Scope scope(current_dispatch, &active);
        assert(current_winner(Axis::X).source == Source::Mouse);
        assert(current_winner(Axis::Y).source == Source::Unknown);
        try {
            Dispatch unknown{};
            Scope nested(current_dispatch, &unknown);
            assert(current_winner(Axis::X).source == Source::Unknown);
            throw std::runtime_error("dispatch unwind");
        } catch (...) {}
        assert(current_winner(Axis::X).source == Source::Mouse);
        e.record(outer, &action, &instance, {});
        assert(current_winner(Axis::X).source == Source::Unknown); // Snapshot invalidated.
        e.record(outer, &action, &instance, {Source::Mouse, Axis::X});
        for (auto who : {&owner, &other_owner})
        {
            e.reset(who, inner_frame);
            const auto inner = e.generation;
            assert(inner.number > outer.number && !e.matches(outer));
            assert(current_winner(Axis::X).source == Source::Unknown);
            e.record(outer, &action, &instance, {Source::Gamepad, Axis::X});
            assert(e.count == 0); // Resumed outer cannot populate inner generation.
            e.record(inner, &action, &instance, {Source::Mouse, Axis::X});
            assert(e.lookup(inner, &action, &instance).source == Source::Mouse);
            assert(e.capture(who, outer_frame).number == 0);
        }
        // Same stack address and owner reused by a later invocation still cannot
        // revive a stale dispatch: generation, not just frame identity, must match.
        e.reset(&owner, outer_frame);
        e.record(e.generation, &action, &instance, {Source::Mouse, Axis::X});
        assert(current_winner(Axis::X).source == Source::Unknown);
    }
    assert(!current_dispatch && current_winner(Axis::X).source == Source::Unknown);
    std::thread separate([] {
        assert(!provenance.valid && provenance.generation.number == 0 && !current_dispatch);
        provenance.reset(reinterpret_cast<void*>(1), 0x10000);
        assert(provenance.generation.number == 1);
    });
    separate.join();
    assert(e.generation.number > 1);
    int actions[129]{};
    e.reset(&owner, outer_frame);
    for (auto& key : actions) e.record(e.generation, &key, &instance, {Source::Mouse, Axis::X});
    assert(!e.valid);
    e.reset(nullptr, outer_frame); assert(!e.valid);
    e.reset(&owner, 0); assert(!e.valid);
    e.reset(&owner, outer_frame + 1); assert(!e.valid);
    e.reset(&owner, outer_frame); assert(e.valid && e.count == 0);
    e.generation.number = std::numeric_limits<std::uint64_t>::max() - 1;
    e.reset(&owner, outer_frame);
    assert(e.valid && e.generation.number == std::numeric_limits<std::uint64_t>::max());
    const auto last = e.generation;
    e.reset(&owner, outer_frame);
    assert(!e.valid && e.exhausted && !e.matches(last));
    e.reset(&owner, inner_frame);
    assert(!e.valid && e.generation.number == last.number); // No ABA after wrap.
    std::puts("PASS: reset, rollover fail-closed, nested invalidation, stale generations, replacement/Unknown, dispatch masking, identity/axis gates, no-dispatch fallback, overflow, invalid frames, TLS isolation");
}
