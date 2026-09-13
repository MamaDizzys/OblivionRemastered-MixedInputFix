#pragma once

// Compile-time-only observer. No gameplay helpers call this recorder. The mapped
// file and its handles are retained until process termination, like hook storage.
// Recording performs bounded, lock-free memory operations only, including under
// loader lock and while other threads are suspended. No CRT, TLS, OS calls,
// allocation, formatting, waits, flushing, exception handlers or cleanup here.
#if MIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC
#include <Windows.h>
#include <intrin.h>
#include <cstdint>
#include <cstddef>

namespace mixed_input::shutdown
{
enum Event : unsigned
{
    opened = 1, installed, uninstall_enter, destructor_enter, overrides_disabled,
    restore_begin, collect_begin, collect_end, pause_begin, pause_end,
    bytes_checked, pages_writable, bytes_written, cache_flushed, rollback,
    protections_restored, resume_begin, resume_end, commit_result,
    destructor_body_end, uninstall_delete_complete, restore_exception,
    dll_detach_enter, dll_detach_return,
    bridge_destructor_enter, winner_unwind_begin, winner_unwind_end,
    reset_unwind_begin, reset_unwind_end, bridge_free_begin, bridge_free_end,
    bridge_destructor_end, trampoline_destructor_enter, trampoline_destructor_end,
    restore_rejected,
};
struct Entry
{
    volatile LONG sequence;
    unsigned event;
    std::uint64_t thread, a, b;
};
struct Journal
{
    char magic[8];
    unsigned version, capacity, pid;
    volatile LONG count;
    std::uint64_t module, game, bridge, installation;
    std::uint64_t reserved;
    Entry entries[128];
};
static_assert(sizeof(Entry) == 32 && offsetof(Journal, entries) == 64);
inline constinit Journal* journal{};

inline void record(Event event, std::uint64_t a = 0, std::uint64_t b = 0) noexcept
{
    auto* const p = journal;
    if (!p) return;
    const auto index = _InterlockedIncrement(&p->count) - 1;
    if (index < 0 || index >= 128) return;
    auto& e = p->entries[index];
    e.event = event;
    e.thread = __readgsqword(0x48); // Win64 TEB.ClientId.UniqueThread; no TLS helper.
    e.a = a;
    e.b = b;
    _InterlockedExchange(&e.sequence, index + 1); // Publish the complete record last.
}
bool open() noexcept;
}
#define MIF_SHUTDOWN(event, a, b) ::mixed_input::shutdown::record(::mixed_input::shutdown::event, a, b)
#else
#define MIF_SHUTDOWN(event, a, b) ((void)0)
#endif
