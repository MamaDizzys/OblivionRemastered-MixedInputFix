#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace mixed_input
{
// Camera and movement domains stay distinct, including on the same axis.
enum class Source : std::uint8_t { Unknown, Mouse, Gamepad, Digital, LeftStick };
enum class Axis : std::uint8_t { Unknown, X, Y };
struct Winner { Source source{}; Axis axis{}; };
struct Generation
{
    const void* owner{};
    std::uintptr_t frame{};
    std::uint64_t number{};
};

// Persistent per-thread storage: no pointers to evaluation stack objects and no
// exit cleanup. Every reset discards the preceding generation, including nested
// evaluations. Exhaustion permanently disables this thread rather than reuse a
// generation number that an old synchronous dispatch could still hold.
struct Evaluation
{
    struct Entry { const void* action; const void* instance; Winner winner; };
    Generation generation{};
    std::array<Entry, 128> entries{};
    std::size_t count{};
    bool valid{};
    bool exhausted{};

    void reset(const void* owner, std::uintptr_t frame) noexcept
    {
        valid = false;
        count = 0;
        generation.owner = owner;
        generation.frame = frame;
        if (exhausted || generation.number == std::numeric_limits<std::uint64_t>::max())
        { exhausted = true; return; }
        ++generation.number;
        valid = owner && frame >= 0x10000 && !(frame & 15);
    }
    bool matches(Generation token) const noexcept
    {
        return valid && token.number && token.number == generation.number &&
            token.owner == generation.owner && token.frame == generation.frame;
    }
    Generation capture(const void* owner, std::uintptr_t frame) const noexcept
    {
        return valid && owner == generation.owner && frame == generation.frame ? generation : Generation{};
    }
    void record(Generation token, const void* action, const void* instance, Winner winner) noexcept
    {
        if (!matches(token)) return;
        if (!action || !instance) { valid = false; return; }
        for (std::size_t i = 0; i < count; ++i)
            if (entries[i].action == action)
            { entries[i] = {action, instance, winner}; return; }
        if (count == entries.size()) { valid = false; return; }
        entries[count++] = {action, instance, winner};
    }
    Winner lookup(Generation token, const void* action, const void* instance) const noexcept
    {
        if (matches(token))
            for (std::size_t i = 0; i < count; ++i)
                if (entries[i].action == action && entries[i].instance == instance)
                    return entries[i].winner;
        return {};
    }
};

struct Dispatch
{
    Generation generation{};
    const void* action{};
    const void* instance{};
    Winner winner{};
};

inline constinit thread_local Evaluation provenance{};
inline constinit thread_local Dispatch* current_dispatch{};

template <typename T> struct Scope
{
    T*& slot;
    T* previous;
    Scope(T*& slot_, T* value) noexcept : slot(slot_), previous(slot_) { slot = value; }
    ~Scope() { slot = previous; }
    Scope(const Scope&) = delete;
    Scope& operator=(const Scope&) = delete;
};

inline Winner current_winner(Axis axis) noexcept
{
    const auto* d = current_dispatch;
    if (!d || !provenance.matches(d->generation) || !d->action || !d->instance || d->winner.axis != axis)
        return {};
    const auto now = provenance.lookup(d->generation, d->action, d->instance);
    if (now.source != d->winner.source || now.axis != d->winner.axis) return {};
    return d->winner;
}
}
