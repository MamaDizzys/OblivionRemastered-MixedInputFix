#define NOMINMAX
#include <Windows.h>
#include <TlHelp32.h>
#include <array>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <vector>
#include <asmjit/asmjit.h>
#include <polyhook2/Detour/x64Detour.hpp>
#ifndef MIXED_INPUT_FIX_TEST
#include <Mod/CppUserModBase.hpp>
#endif
#include "Provenance.hpp"
#include "Sites.hpp"
#include "DiagnosticStage.hpp"
#include "ShutdownDiagnostic.hpp"
#ifndef MIXED_INPUT_FIX_CAMERA_PROTOTYPE
#define MIXED_INPUT_FIX_CAMERA_PROTOTYPE 0
#endif
#ifndef MIXED_INPUT_FIX_DIAGNOSTICS
#define MIXED_INPUT_FIX_DIAGNOSTICS (MIXED_INPUT_FIX_CAMERA_PROTOTYPE || MIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC)
#endif

#if MIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC
bool mixed_input::shutdown::open() noexcept
{
    HMODULE self{};
    wchar_t path[32768]{};
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&open), &self)) return false;
    const auto length = GetModuleFileNameW(self, path, static_cast<DWORD>(std::size(path)));
    constexpr wchar_t suffix[] = L".shutdown.bin";
    if (!length || length + std::size(suffix) > std::size(path)) return false;
    std::memcpy(path + length, suffix, sizeof(suffix));
    // Refuse to overwrite evidence from an earlier launch.
    const auto file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                                 nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    const auto mapping = CreateFileMappingW(file, nullptr, PAGE_READWRITE, 0, 8192, nullptr);
    if (!mapping) { CloseHandle(file); return false; }
    auto* view = MapViewOfFile(mapping, FILE_MAP_READ | FILE_MAP_WRITE, 0, 0, 8192);
    if (!view) { CloseHandle(mapping); CloseHandle(file); return false; }
    auto* p = new (view) Journal{};
    std::memcpy(p->magic, "MIFEXIT1", 8);
    p->version = 1;
    p->capacity = 128;
    p->pid = GetCurrentProcessId();
    p->module = reinterpret_cast<std::uintptr_t>(self);
    p->game = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
    journal = p;
    record(opened);
    return true;
}
#endif

namespace mixed_input
{
namespace
{
std::uintptr_t base{};
std::uint64_t evaluation_trampoline{};
std::atomic_bool enabled{};
using Evaluate = void (*)(void* owner, void* components, float delta, bool paused, void* work_list);
using Execute = void (*)(void*, void*);
using Getter = std::uint8_t (*)(void*);

// Opened before publishing hooks and retained with the pinned callback storage.
// Hook helpers only write fixed literals once; no CRT/UE4SS logger, formatting,
// heap allocation or application locks on the callback path.
HANDLE diagnostic_file = INVALID_HANDLE_VALUE;
std::atomic_flag evaluation_seen{}, evaluation_returned{}, input_x_seen{}, input_y_seen{};
static_assert(std::atomic_bool::is_always_lock_free);

#if MIXED_INPUT_FIX_DIAGNOSTICS
void open_diagnostics() noexcept
{
    HMODULE self{};
    wchar_t path[32768]{};
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&open_diagnostics), &self)) return;
    const auto length = GetModuleFileNameW(self, path, static_cast<DWORD>(std::size(path)));
    constexpr wchar_t suffix[] = L".diagnostic.log";
    if (!length || length + std::size(suffix) > std::size(path)) return;
    std::memcpy(path + length, suffix, sizeof(suffix));
    diagnostic_file = CreateFileW(path, FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH, nullptr);
}

template <std::size_t N> void diagnostic(const char (&message)[N]) noexcept
{
    const auto last_error = GetLastError();
    if (diagnostic_file != INVALID_HANDLE_VALUE)
    {
        DWORD written{};
        WriteFile(diagnostic_file, message, static_cast<DWORD>(N - 1), &written, nullptr);
    }
    OutputDebugStringA(message);
    SetLastError(last_error);
}
template <std::size_t N> void first_execution(std::atomic_flag& seen, const char (&message)[N]) noexcept
{
    if (!seen.test_and_set(std::memory_order_relaxed)) diagnostic(message);
}

#else
void open_diagnostics() noexcept {}
template <std::size_t N> void diagnostic(const char (&)[N]) noexcept {}
template <std::size_t N> void first_execution(std::atomic_flag&, const char (&)[N]) noexcept {}
#endif

void log(const char* message) noexcept
{
    OutputDebugStringA("[MixedInputFix] ");
    OutputDebugStringA(message);
    OutputDebugStringA("\n");
}

template <typename T> bool read(std::uintptr_t address, T& value) noexcept
{
    if (!address) return false;
    __try { std::memcpy(&value, reinterpret_cast<const void*>(address), sizeof(T)); return true; }
    __except (GetExceptionCode() == EXCEPTION_ACCESS_VIOLATION ||
              GetExceptionCode() == EXCEPTION_IN_PAGE_ERROR ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH)
    { return false; }
}

bool action_info(const void* instance, const void*& action) noexcept
{
    std::uint8_t type{}, policy{};
    const auto p = reinterpret_cast<std::uintptr_t>(instance);
    return read(p, action) && action && read(p + 0x50, type) && type == 1 &&
           read(reinterpret_cast<std::uintptr_t>(action) + 0x51, policy) && policy == 0;
}

Winner classify(std::uintptr_t key) noexcept
{
    // This shipping build uses an eight-byte FName (comparison index + number).
    // Compare the full identity, reading engine EKeys globals on every invocation.
    std::uint64_t name{}, mx{}, my{}, gx{}, gy{};
    if (!read(key, name) || !name || !read(base + sites::mouse_x, mx) ||
        !read(base + sites::mouse_y, my) || !read(base + sites::gamepad_x, gx) ||
        !read(base + sites::gamepad_y, gy) || !mx || !my || !gx || !gy ||
        mx == my || mx == gx || mx == gy || my == gx || my == gy || gx == gy)
        return {};
    if (name == mx) return {Source::Mouse, Axis::X};
    if (name == my) return {Source::Mouse, Axis::Y};
    if (name == gx) return {Source::Gamepad, Axis::X};
    if (name == gy) return {Source::Gamepad, Axis::Y};
    return {};
}

Winner classify_movement(std::uintptr_t key, std::uintptr_t frame) noexcept
{
    std::uint64_t name{}, details_name{}, lx{}, ly{};
    std::uintptr_t details{};
    std::uint8_t key_type{}, mapped_type{};
    double candidate{};
    // The physical caller already resolves FKey details (0x392BAE8). No
    // engine calls or lazy metadata writes here. Details embed the same FKey.
    // +42: 0=digital, 1=button axis, 2=1D, 3=2D, 4=3D. Reject unsupported types.
    if (!read(key, name) || !name || !read(key + 8, details) || !details ||
        !read(details, details_name) || details_name != name ||
        !read(details + 0x42, key_type) || !read(frame - 0x31, mapped_type) || mapped_type != 1 ||
        !read(frame - 0x49, candidate)) return {};
    std::uint64_t bits{};
    std::memcpy(&bits, &candidate, sizeof(bits));
    if ((bits & 0x7FF0000000000000ULL) == 0x7FF0000000000000ULL) return {};
    if (!read(base + sites::left_x, lx) || !lx ||
        !read(base + sites::left_y, ly) || !ly || lx == ly) return {};
    if (name == lx) return key_type == 2 ? Winner{Source::LeftStick, Axis::X} : Winner{};
    if (name == ly) return key_type == 2 ? Winner{Source::LeftStick, Axis::Y} : Winner{};
    if (key_type == 0 && candidate >= 0) return {Source::Digital, Axis::Unknown};
    return {};
}

#include "CameraComposition.hpp"
#include "CameraSites.hpp"

// Called only by the reset shim. No logging, allocation, exceptions or game calls.
// Reset CALL entry RSP = evaluation entry S-0x640; RBP = S-0x538.
void reset_generation(void* owner, std::uintptr_t frame, std::uintptr_t reset_rsp) noexcept
{
    provenance.reset(owner, frame);
    if (frame < 0x108 || frame - 0x108 != reset_rsp) provenance.valid = false;
}

void record_winner(std::uintptr_t frame, void* owner, void* instance, std::uint64_t component) noexcept
{
    if (!enabled.load(std::memory_order_acquire)) return;
    auto& e = provenance;
    std::uintptr_t evaluation_frame{};
    // Mapping RBP = mapping entry RSP-0x3F; PUSH RBP saved its caller at S-8.
    if (!read(frame + 0x37, evaluation_frame)) { e.valid = false; return; }
    const auto token = e.capture(owner, evaluation_frame);
    if (!e.matches(token)) { e.valid = false; return; }
    const void* action{};
    const void* frame_action{};
    std::uintptr_t caller{}, key{};
    if (!read(reinterpret_cast<std::uintptr_t>(instance), action) || !action)
    { e.valid = false; return; }
    Winner winner{};
    const void* checked_action{};
    if (component == 0 && action_info(instance, checked_action) && checked_action == action &&
        read(frame + 0x4F, frame_action) && frame_action == action &&
        read(frame + 0x3F, caller) && caller == base + sites::mapping_return &&
        read(frame + 0x1F, key))
    {
        winner = classify(key);
        if (winner.source == Source::Unknown) winner = classify_movement(key, frame);
    }
    // Foreign/unknown mappings replace old winners. Mismatched evaluation frames
    // invalidate the table, so resumed outer work cannot populate an inner reset.
    e.record(token, action, instance, winner);
}

// Optional companion to the pure Stage 1A tail jump. This still assumes the
// declared five-argument/void ABI and introduces a C++ call frame. It deliberately
// does not read/write any provenance TLS or construct an Evaluation/Scope.
// Keeping work_list live across diagnostics makes the compiler preserve it from
// incoming entry-RSP+28h and explicitly populate outgoing RSP+20h for the game
// CALL. WriteFile's fifth argument uses our outgoing area, not the caller's.
void evaluate_trace(void* owner, void* components, float delta, bool paused, void* work_list)
{
    first_execution(evaluation_seen, "[MixedInputFix] First execution: evaluation trace (no scopes)\n");
    reinterpret_cast<Evaluate>(evaluation_trampoline)(owner, components, delta, paused, work_list);
    first_execution(evaluation_returned, "[MixedInputFix] First normal return: evaluation trace (no scopes)\n");
}

void dispatch(void* binding, void* instance, void* owner, std::uintptr_t frame)
{
    Dispatch context{};
    context.instance = instance;
    context.generation = provenance.capture(owner, frame);
    if (enabled.load(std::memory_order_acquire) && action_info(instance, context.action))
        context.winner = provenance.lookup(context.generation, context.action, instance);
    // Every synchronous dispatch masks its parent, including Unknown/mismatched.
    Scope scope(current_dispatch, &context);
    const auto vtable = *static_cast<Execute**>(binding);
    vtable[1](binding, instance); // Preserve original virtual target, exactly once.
}

std::uint8_t input_type(void* object, Axis axis) noexcept
{
    std::uint8_t subcall_type{};
    if (camera_composition::source_override(axis, subcall_type)) return subcall_type;
    if (enabled.load(std::memory_order_acquire))
    {
        const void* action{};
        const auto* d = current_dispatch;
        if (d && action_info(d->instance, action) && action == d->action)
        {
            const auto winner = current_winner(axis);
            if (winner.source == Source::Mouse) return 0;
            if (winner.source == Source::Gamepad) return 1;
        }
    }
    return reinterpret_cast<Getter>(base + sites::getter)(object);
}
std::uint8_t input_x(void* object) noexcept
{
    first_execution(input_x_seen, "[MixedInputFix] First execution: horizontal getter helper\n");
    return input_type(object, Axis::X);
}
std::uint8_t input_y(void* object) noexcept
{
    first_execution(input_y_seen, "[MixedInputFix] First execution: vertical getter helper\n");
    return input_type(object, Axis::Y);
}

std::uint8_t movement_type(void* object, Axis axis) noexcept
{
    if (enabled.load(std::memory_order_acquire))
    {
        const auto* d = current_dispatch;
        const void* action{};
        if (d && action_info(d->instance, action) && action == d->action)
        {
            if (current_winner(Axis::Unknown).source == Source::Digital) return 0;
            if (current_winner(axis).source == Source::LeftStick) return 1;
        }
    }
    return reinterpret_cast<Getter>(base + sites::getter)(object);
}
std::uint8_t movement_x(void* object) noexcept { return movement_type(object, Axis::X); }
std::uint8_t movement_y(void* object) noexcept { return movement_type(object, Axis::Y); }

struct Patch
{
    std::uintptr_t rva{};
    std::size_t size{};
    std::array<std::uint8_t, 32> before{}, after{};
};
std::vector<std::uint8_t> decode(const char* text)
{
    std::vector<std::uint8_t> bytes;
    unsigned byte{};
    while (*text)
    {
        if (std::sscanf(text, "%2x", &byte) != 1) throw std::runtime_error("Invalid signature");
        bytes.push_back(static_cast<std::uint8_t>(byte));
        text += 2;
        if (*text == ' ') ++text;
    }
    return bytes;
}
bool matches(std::uintptr_t address, const void* bytes, std::size_t size) noexcept
{
    std::array<std::uint8_t, 128> actual{};
    SIZE_T count{};
    return size <= actual.size() && ReadProcessMemory(GetCurrentProcess(), reinterpret_cast<void*>(address),
        actual.data(), size, &count) && count == size && !std::memcmp(actual.data(), bytes, size);
}

// Use PolyHook's decoder/relocator to prepare the seven-byte entry trampoline.
// Supply our own nearby jump slot, avoiding dependence on VirtualAlloc2 and
// selecting the actual JMP from this bundled API's {slot, JMP} result.
// Preparation never writes the game entry.
class PreparedDetour final : public PLH::x64Detour
{
    std::uintptr_t entry_;
    std::uintptr_t slot_;
public:
    std::array<std::uint8_t, 7> bytes{};
    PreparedDetour(std::uintptr_t entry, std::uintptr_t callback, std::uintptr_t slot) :
        x64Detour(entry, callback, &evaluation_trampoline), entry_(entry), slot_(slot) {}
    ~PreparedDetour() override
    {
        MIF_SHUTDOWN(trampoline_destructor_enter, m_trampoline, 0);
        // hook() was never called, so the base will not unhook game memory.
        if (m_trampoline) delete[] reinterpret_cast<std::uint8_t*>(m_trampoline);
        m_trampoline = 0;
        evaluation_trampoline = 0;
        MIF_SHUTDOWN(trampoline_destructor_end, 0, 0);
    }
    PLH::ProtFlag mem_protect(std::uint64_t dest, std::uint64_t size, PLH::ProtFlag prot, bool& ok) const override
    {
        const auto previous = PLH::MemAccessor::mem_protect(dest, size, prot, ok);
        if (!ok) throw std::runtime_error("PolyHook trampoline protection failed");
        return previous;
    }
    bool prepare()
    {
        const auto delta = static_cast<std::int64_t>(slot_) - static_cast<std::int64_t>(entry_ + 6);
        if (delta < INT32_MIN || delta > INT32_MAX) return false;
        auto instructions = m_disasm.disassemble(entry_, entry_, entry_ + 7, *this);
        std::uint64_t rounded{};
        auto prologue = calcNearestSz(instructions, 6, rounded);
        if (!prologue || rounded != 7 || prologue->size() != 2 ||
            prologue->at(0).size() != 3 || prologue->at(1).size() != 4 ||
            prologue->at(0).hasDisplacement() || prologue->at(1).hasDisplacement()) return false;
        PLH::insts_t jump_table;
        if (!makeTrampoline(*prologue, jump_table)) return false;
        // This specific prologue needs no rebasing: MOV RAX,RSP (3), then
        // MOV [RAX+20h],R9B (4). The +20h is a register-based memory offset.
        // The generated jump back must be FF 25 disp32, preserving RAX/RSP,
        // through an in-allocation pointer containing precisely entry+7.
        if (!verify_trampoline()) return false;
        if (!FlushInstructionCache(GetCurrentProcess(), reinterpret_cast<void*>(m_trampoline), m_trampolineSz)) return false;
        const auto jump = PLH::makex64MinimumJump(entry_, m_fnCallback, slot_);
        // This bundled API returns {eight-byte destination slot, six-byte JMP}.
        if (jump.size() != 2 || jump.back().size() != 6) return false;
        const auto encoding = jump.back().getBytes();
        std::memcpy(bytes.data(), encoding.data(), 6);
        bytes[6] = 0x90;
        evaluation_trampoline = m_trampoline;
        return true;
    }
    bool verify_trampoline() const noexcept
    {
        constexpr std::uint8_t prefix[]{0x48, 0x8B, 0xC4, 0x44, 0x88, 0x48, 0x20, 0xFF, 0x25};
        if (m_trampolineSz < 21 || !matches(m_trampoline, prefix, sizeof(prefix))) return false;
        std::int32_t displacement{};
        if (!read(m_trampoline + 9, displacement)) return false;
        const auto slot = static_cast<std::uintptr_t>(static_cast<std::int64_t>(m_trampoline + 13) + displacement);
        if (slot < m_trampoline + 13 || slot > m_trampoline + m_trampolineSz - sizeof(std::uintptr_t)) return false;
        std::uintptr_t continuation{};
        return read(slot, continuation) && continuation == entry_ + 7;
    }
};

struct AsmErrors final : asmjit::ErrorHandler
{
    void handleError(asmjit::Error, const char* message, asmjit::BaseEmitter*) override
    { throw std::runtime_error(message); }
};
void check(asmjit::Error error)
{
    if (error) throw std::runtime_error(asmjit::DebugUtils::errorAsString(error));
}

class Bridges
{
public:
    std::uint8_t* memory{};
    std::array<RUNTIME_FUNCTION, 3> unwind{};
    bool registered{};
    std::array<RUNTIME_FUNCTION, 3> reset_unwind{};
    bool reset_registered{};
    std::size_t reset_body{}, reset_pop_flags{}, reset_tail{}, reset_size{};
    static constexpr std::size_t size = 0x3000;
    RUNTIME_FUNCTION camera_unwind{};
    bool camera_registered{};
    ~Bridges()
    {
        if (camera_registered) RtlDeleteFunctionTable(&camera_unwind);
        MIF_SHUTDOWN(bridge_destructor_enter, at(0), 0);
        if (registered)
        {
            MIF_SHUTDOWN(winner_unwind_begin, at(0), 0);
            const auto result = RtlDeleteFunctionTable(unwind.data());
            MIF_SHUTDOWN(winner_unwind_end, result, 0);
            (void)result;
        }
        if (reset_registered)
        {
            MIF_SHUTDOWN(reset_unwind_begin, at(0), 0);
            const auto result = RtlDeleteFunctionTable(reset_unwind.data());
            MIF_SHUTDOWN(reset_unwind_end, result, 0);
            (void)result;
        }
        if (memory)
        {
            MIF_SHUTDOWN(bridge_free_begin, at(0), 0);
            const auto result = VirtualFree(memory, 0, MEM_RELEASE);
            MIF_SHUTDOWN(bridge_free_end, result, 0);
            (void)result;
        }
        MIF_SHUTDOWN(bridge_destructor_end, 0, 0);
    }
    std::uintptr_t at(std::size_t offset) const { return reinterpret_cast<std::uintptr_t>(memory) + offset; }
    // Preparation only: the page has not been published to game threads yet.
    void set_evaluation_target(std::uintptr_t target)
    {
        DWORD old{}, ignored{};
        if (!VirtualProtect(memory, size, PAGE_READWRITE, &old))
            throw std::runtime_error("Cannot prepare evaluation destination slot");
        std::memcpy(memory + 0xA00, &target, sizeof(target));
        if (!VirtualProtect(memory, size, old, &ignored) || !FlushInstructionCache(GetCurrentProcess(), memory, size))
            throw std::runtime_error("Cannot finalize evaluation destination slot");
    }
    template <typename Emit> std::size_t emit(std::size_t offset, Emit emit_code)
    {
        asmjit::CodeHolder code;
        AsmErrors errors;
        check(code.init(asmjit::Environment::host(), at(offset)));
        code.setErrorHandler(&errors);
        asmjit::x86::Assembler a(&code);
        emit_code(a);
        check(code.flatten());
        check(code.resolveUnresolvedLinks());
        check(code.relocateToBase(at(offset)));
        if (code.codeSize() > 0x200) throw std::runtime_error("Bridge too large");
        check(code.copyFlattenedData(memory + offset, code.codeSize()));
        return code.codeSize();
    }
    void build(unsigned stage = diagnostic_stage, EvaluationMode mode = EvaluationMode::Reset)
    {
        if (stage > 4) throw std::runtime_error("Invalid diagnostic stage");
        if (stage == 0) return;
        // Every patch site must reach this page via rel32. Explicit address requests
        // also work on Wine versions whose VirtualAlloc2 range handling is incomplete.
        SYSTEM_INFO info{};
        GetSystemInfo(&info);
        const auto step = static_cast<std::uintptr_t>(info.dwAllocationGranularity);
        const auto center = (base + 0x4000000) & ~(step - 1);
        for (std::uintptr_t distance = step; distance < 0x40000000 && !memory; distance += step)
            for (auto address : {center + distance, center - distance})
                if ((memory = static_cast<std::uint8_t*>(VirtualAlloc(reinterpret_cast<void*>(address), size,
                    MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE)))) break;
        if (!memory) throw std::runtime_error("Cannot allocate near bridges");
        using namespace asmjit::x86;
        std::size_t pop_flags{}, return_offset{};
        const auto winner_size = stage >= 2 ? emit(0, [&](auto& a) {
            // Original RSP is 16-aligned. Patched CALL pushes 8, PUSHFQ pushes 8;
            // 0xC0 bytes include the mandatory 32-byte Windows call home area.
            a.pushfq();
            a.sub(rsp, 0xC0);
            const Gp regs[] = {rax, rcx, rdx, r8, r9, r10, r11};
            for (int i = 0; i < 7; ++i) a.mov(qword_ptr(rsp, 0x20 + i * 8), regs[i]);
            for (int i = 0; i < 6; ++i) a.movdqu(ptr(rsp, 0x60 + i * 16), xmm(i));
            a.mov(r9, rcx);
            a.mov(rcx, rbp);
            a.mov(rdx, r14);
            a.mov(r8, rdi);
            a.mov(rax, reinterpret_cast<std::uint64_t>(&record_winner));
            a.call(rax);
            for (int i = 0; i < 6; ++i) a.movdqu(xmm(i), ptr(rsp, 0x60 + i * 16));
            for (int i = 0; i < 7; ++i) a.mov(regs[i], qword_ptr(rsp, 0x20 + i * 8));
            // Replay the ONE displaced winning store with the original registers.
            a.movsd(qword_ptr(rbp, rcx, 3, -0x69), xmm2);
            a.add(rsp, 0xC0);
            pop_flags = a.offset();
            a.popfq();
            return_offset = a.offset();
            a.ret();
        }) : 0;
        if (stage >= 3) emit(0x200, [](auto& a) {
            a.mov(r9, rbp);
            a.mov(r8, r13);
            a.mov(rax, reinterpret_cast<std::uint64_t>(&dispatch));
            a.jmp(rax); // Leaf adapter; helper returns directly into the game.
        });
        if (stage >= 4)
        {
            emit(0x400, [](auto& a) { a.mov(rax, reinterpret_cast<std::uint64_t>(&input_x)); a.jmp(rax); });
            emit(0x600, [](auto& a) { a.mov(rax, reinterpret_cast<std::uint64_t>(&input_y)); a.jmp(rax); });
            emit(0xC00, [](auto& a) { a.mov(rax, reinterpret_cast<std::uint64_t>(&movement_x)); a.jmp(rax); });
            emit(0xE00, [](auto& a) { a.mov(rax, reinterpret_cast<std::uint64_t>(&movement_y)); a.jmp(rax); });
        }
        // UNWIND_INFO: PUSHFQ (one 8-byte allocation), SUB RSP,0xC0.
        // The only non-leaf bridge changes no nonvolatile registers.
        const std::uint8_t unwind_info[] = {1, 8, 3, 0, 8, 1, 24, 0, 1, 2, 0, 0};
        std::memcpy(memory + 0x800, unwind_info, sizeof(unwind_info));
        // POPFQ is not a Windows-recognized epilogue POP. Describe the two
        // remaining stack states separately so asynchronous stack walks work
        // at POPFQ and RET as well as while the C++ helper is running.
        const std::uint8_t flags_unwind[] = {1, 0, 1, 0, 0, 2, 0, 0};
        const std::uint8_t leaf_unwind[] = {1, 0, 0, 0};
        std::memcpy(memory + 0x820, flags_unwind, sizeof(flags_unwind));
        std::memcpy(memory + 0x840, leaf_unwind, sizeof(leaf_unwind));
        if (mode == EvaluationMode::Reset)
        {
            emit(0xB00, [&](auto& a) {
                // T = incoming RSP (8 modulo 16), with the original game return
                // address at [T]. Everything we write is below T. The helper's
                // home area is [RSP,RSP+20h), GPR saves start at +20h, and the
                // 16-aligned 512-byte FXSAVE64 area starts at +60h.
                a.pushfq();
                a.sub(rsp, 0x260);
                reset_body = a.offset();
                const Gp regs[]{rax, rcx, rdx, r8, r9, r10, r11};
                for (int i = 0; i < 7; ++i) a.mov(qword_ptr(rsp, 0x20 + i * 8), regs[i]);
                a.fxsave64(ptr(rsp, 0x60)); // x87, all 16 XMM registers, MXCSR.
                a.cld();
                a.mov(rcx, r13);
                a.mov(rdx, rbp);
                a.lea(r8, ptr(rsp, 0x268));
                a.mov(rax, reinterpret_cast<std::uint64_t>(&reset_generation));
                a.call(rax);
                a.fxrstor64(ptr(rsp, 0x60));
                for (int i = 0; i < 7; ++i) a.mov(regs[i], qword_ptr(rsp, 0x20 + i * 8));
                a.add(rsp, 0x260);
                reset_pop_flags = a.offset();
                a.popfq();
                reset_tail = a.offset();
                const auto original = a.newLabel();
                a.jmp(qword_ptr(original)); // No register clobber, no extra CALL.
                reset_size = a.offset();
                a.bind(original);
                a.embedUInt64(base + sites::reset_original);
            });
            const std::uint8_t reset_info[]{1, 8, 3, 0, 8, 1, 76, 0, 1, 2, 0, 0};
            std::memcpy(memory + 0x880, reset_info, sizeof(reset_info));
            std::memcpy(memory + 0x8A0, flags_unwind, sizeof(flags_unwind));
            std::memcpy(memory + 0x8C0, leaf_unwind, sizeof(leaf_unwind));
            const DWORD starts[]{0xB00, static_cast<DWORD>(0xB00 + reset_pop_flags), static_cast<DWORD>(0xB00 + reset_tail)};
            const DWORD ends[]{starts[1], starts[2], static_cast<DWORD>(0xB00 + reset_size)};
            for (std::size_t i = 0; i < reset_unwind.size(); ++i)
            {
                reset_unwind[i].BeginAddress = starts[i];
                reset_unwind[i].EndAddress = ends[i];
                reset_unwind[i].UnwindData = static_cast<DWORD>(0x880 + i * 0x20);
            }
            if (!RtlAddFunctionTable(reset_unwind.data(), static_cast<DWORD>(reset_unwind.size()), at(0)))
                throw std::runtime_error("Cannot register reset shim unwind info");
            reset_registered = true;
        }
        const auto evaluation_callback = mode == EvaluationMode::Reset ? 0 : reinterpret_cast<std::uintptr_t>(&evaluate_trace);
        std::memcpy(memory + 0xA00, &evaluation_callback, sizeof(evaluation_callback));
        const auto winner_callback = stage >= 2 ? at(0) : 0;
        const auto dispatch_callback = stage >= 3 ? at(0x200) : 0;
        std::memcpy(memory + 0xA08, &winner_callback, sizeof(winner_callback));
        std::memcpy(memory + 0xA10, &dispatch_callback, sizeof(dispatch_callback));
        unwind[0].BeginAddress = 0;
        unwind[0].EndAddress = static_cast<DWORD>(pop_flags);
        unwind[0].UnwindData = 0x800;
        unwind[1].BeginAddress = static_cast<DWORD>(pop_flags);
        unwind[1].EndAddress = static_cast<DWORD>(return_offset);
        unwind[1].UnwindData = 0x820;
        unwind[2].BeginAddress = static_cast<DWORD>(return_offset);
        unwind[2].EndAddress = static_cast<DWORD>(winner_size);
        unwind[2].UnwindData = 0x840;
        if (stage >= 2)
        {
            if (!RtlAddFunctionTable(unwind.data(), static_cast<DWORD>(unwind.size()), at(0)))
                throw std::runtime_error("Cannot register bridge unwind info");
            registered = true;
        }
        if (stage == 4 && mode == EvaluationMode::Reset)
        {
            using namespace camera_composition;
            const auto camera_size = emit(0x1000, [](auto& a) {
                // Seven-argument wrapper: preserve all native five arguments, add
                // mapping RBP and instance RDI below incoming RSP. No caller-slot writes.
                a.sub(rsp,0x48);
                a.movss(xmm0,dword_ptr(rsp,0x70));
                a.movss(dword_ptr(rsp,0x20),xmm0);
                a.mov(qword_ptr(rsp,0x28),rbp);
                a.mov(qword_ptr(rsp,0x30),rdi);
                a.mov(rax,reinterpret_cast<std::uint64_t>(&modify)); a.call(rax);
                a.add(rsp,0x48); a.ret();
            });
            const std::uint8_t camera_info[]{1,4,1,0,4,0x82,0,0}; // sub rsp,72
            std::memcpy(memory+0x2800,camera_info,sizeof(camera_info));
            camera_unwind.BeginAddress=0x1000;
            camera_unwind.EndAddress=static_cast<DWORD>(0x1000+camera_size);
            camera_unwind.UnwindData=0x2800;
            if (!RtlAddFunctionTable(&camera_unwind,1,at(0))) throw std::runtime_error("Camera composition unwind registration failed");
            camera_registered=true;
            const std::uintptr_t targets[]{reinterpret_cast<std::uintptr_t>(&camera<Axis::X>),
                reinterpret_cast<std::uintptr_t>(&camera<Axis::Y>),reinterpret_cast<std::uintptr_t>(&clear<Axis::X>),
                reinterpret_cast<std::uintptr_t>(&clear<Axis::Y>),reinterpret_cast<std::uintptr_t>(&angular<Axis::X,Source::Gamepad>),
                reinterpret_cast<std::uintptr_t>(&angular<Axis::X,Source::Mouse>),reinterpret_cast<std::uintptr_t>(&angular<Axis::Y,Source::Gamepad>),
                reinterpret_cast<std::uintptr_t>(&angular<Axis::Y,Source::Mouse>),reinterpret_cast<std::uintptr_t>(&tail)};
            for (unsigned i=0;i<std::size(targets);++i)
            {
                emit(0x1200+i*0x100,[&](auto& a) { a.mov(rax,targets[i]); a.jmp(rax); });
                const auto target=at(0x1200+i*0x100); std::memcpy(memory+0x2900+i*8,&target,8);
            }
        }
        DWORD old{};
        if (!VirtualProtect(memory, size, PAGE_EXECUTE_READ, &old) ||
            !FlushInstructionCache(GetCurrentProcess(), memory, size))
            throw std::runtime_error("Cannot finalize executable bridges");
    }
};

// Open handles before suspension. No allocator, logger, PolyHook or AsmJit calls
// occur while threads are paused. An instruction pointer inside a patch aborts.
class PausedThreads
{
    std::vector<HANDLE> threads_;
    std::size_t paused_{};
    bool observing_{};
public:
    explicit PausedThreads(bool observing = false) : observing_(observing) {}
    ~PausedThreads()
    {
        if (observing_) MIF_SHUTDOWN(resume_begin, paused_, threads_.size());
        std::size_t failures{};
        for (std::size_t i = 0; i < paused_; ++i)
            if (ResumeThread(threads_[i]) == DWORD(-1)) ++failures;
        for (auto thread : threads_) CloseHandle(thread);
        if (observing_) MIF_SHUTDOWN(resume_end, paused_, failures);
    }
    bool collect()
    {
        HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
        if (snapshot == INVALID_HANDLE_VALUE) return false;
        THREADENTRY32 entry{};
        entry.dwSize = sizeof(entry);
        bool ok = Thread32First(snapshot, &entry) != FALSE;
        if (ok) do {
            if (entry.th32OwnerProcessID == GetCurrentProcessId() && entry.th32ThreadID != GetCurrentThreadId())
            {
                HANDLE thread = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_LIMITED_INFORMATION,
                                           FALSE, entry.th32ThreadID);
                if (!thread) { ok = false; break; }
                threads_.push_back(thread);
            }
        } while (Thread32Next(snapshot, &entry));
        CloseHandle(snapshot);
        return ok;
    }
    bool pause(const std::vector<Patch>& patches) noexcept
    {
        for (auto thread : threads_)
        {
            if (SuspendThread(thread) == DWORD(-1)) return false;
            ++paused_;
            CONTEXT context{};
            context.ContextFlags = CONTEXT_CONTROL;
            if (!GetThreadContext(thread, &context)) return false;
            for (const auto& patch : patches)
                if (context.Rip >= base + patch.rva && context.Rip < base + patch.rva + patch.size)
                    return false;
        }
        return true;
    }
};

struct Installation
{
    const unsigned stage;
    const EvaluationMode evaluation_mode;
    explicit Installation(unsigned selected_stage = diagnostic_stage, EvaluationMode mode = EvaluationMode::Reset) :
        stage(selected_stage), evaluation_mode(mode)
    {
        if (stage > 4) throw std::runtime_error("Invalid diagnostic stage");
        if (mode != EvaluationMode::Reset && (stage != 1 ||
            (mode != EvaluationMode::Direct && mode != EvaluationMode::Trace)))
            throw std::runtime_error("Evaluation diagnostic variant requires Stage 1");
    }
    Bridges bridges;
    std::unique_ptr<PreparedDetour> detour;
    std::vector<Patch> patches;
    bool installed{};
    bool protection_warning{};

    void add_patch(std::uintptr_t rva, const void* replacement, std::size_t size)
    {
        Patch p{rva, size};
        if (size > p.before.size()) throw std::runtime_error("Patch too large");
        std::memcpy(p.before.data(), reinterpret_cast<void*>(base + rva), size);
        std::memcpy(p.after.data(), replacement, size);
        patches.push_back(p);
    }
    void add_call(std::uintptr_t rva, std::uintptr_t target)
    {
        const auto delta = static_cast<std::int64_t>(target) - static_cast<std::int64_t>(base + rva + 5);
        if (delta < INT32_MIN || delta > INT32_MAX) throw std::runtime_error("Bridge outside rel32 range");
        std::array<std::uint8_t, 5> bytes{0xE8, 0, 0, 0, 0};
        const auto displacement = static_cast<std::int32_t>(delta);
        std::memcpy(bytes.data() + 1, &displacement, sizeof(displacement));
        add_patch(rva, bytes.data(), bytes.size());
    }
    void add_indirect_call(std::uintptr_t rva, std::uintptr_t slot)
    {
        // The return must be +6, the original instruction boundary, even if
        // uninstall restores these bytes while a callback is still executing.
        // E8 rel32 + NOP would return at +5, inside the restored instruction.
        const auto delta = static_cast<std::int64_t>(slot) - static_cast<std::int64_t>(base + rva + 6);
        if (delta < INT32_MIN || delta > INT32_MAX) throw std::runtime_error("Call slot outside rel32 range");
        std::array<std::uint8_t, 6> bytes{0xFF, 0x15, 0, 0, 0, 0};
        const auto displacement = static_cast<std::int32_t>(delta);
        std::memcpy(bytes.data() + 2, &displacement, sizeof(displacement));
        add_patch(rva, bytes.data(), bytes.size());
    }
    bool validate()
    {
        IMAGE_DOS_HEADER dos{};
        IMAGE_NT_HEADERS64 nt{};
        if (!read(base, dos) || dos.e_magic != IMAGE_DOS_SIGNATURE || dos.e_lfanew <= 0 ||
            !read(base + dos.e_lfanew, nt) || nt.Signature != IMAGE_NT_SIGNATURE ||
            nt.FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64 ||
            nt.OptionalHeader.Magic != IMAGE_NT_OPTIONAL_HDR64_MAGIC ||
            nt.OptionalHeader.SizeOfImage <= sites::gamepad_y + 24)
        { log("Unsupported PE image"); return false; }
        for (const auto& signature : sites::signatures)
        {
            const auto bytes = decode(signature.hex);
            if (!matches(base + signature.rva, bytes.data(), bytes.size()))
            {
                char message[200]{};
                std::snprintf(message, sizeof(message), "Validation failed: %s at RVA 0x%llX; no patches installed",
                              signature.name, static_cast<unsigned long long>(signature.rva));
                log(message);
                return false;
            }
        }
        if (stage == 4 && evaluation_mode == EvaluationMode::Reset)
        for (const auto& signature : camera_composition::signatures)
        {
            const auto bytes=decode(signature.hex);
            if (!matches(base+signature.rva,bytes.data(),bytes.size())) { log(signature.name); return false; }
        }
        return true;
    }

    // All pages are made writable before ANY bytes change. Restore protections on
    // every path. A cache-flush failure rolls the whole set back while still paused.
    bool commit(bool install)
    {
        std::vector<std::pair<std::uintptr_t, std::vector<std::uint8_t>>> validations;
        if (install)
            for (const auto& signature : sites::signatures)
                validations.emplace_back(signature.rva, decode(signature.hex));
        if (install && stage == 4 && evaluation_mode == EvaluationMode::Reset)
            for (const auto& signature : camera_composition::signatures)
                validations.emplace_back(signature.rva,decode(signature.hex));
        std::vector<DWORD> protections(patches.size());
        PausedThreads threads(!install);
        if (!install) MIF_SHUTDOWN(collect_begin, patches.size(), 0);
        const auto collected = threads.collect();
        if (!install) MIF_SHUTDOWN(collect_end, collected, collected ? 0 : GetLastError());
        if (!collected) return false;
        if (!install) MIF_SHUTDOWN(pause_begin, 0, 0);
        const auto paused = threads.pause(patches);
        if (!install) MIF_SHUTDOWN(pause_end, paused, paused ? 0 : GetLastError());
        if (!paused) return false;
        // Recheck the entire contract after suspension, not merely byte snapshots
        // taken during preparation (another mod may have changed code meanwhile).
        for (const auto& [rva, bytes] : validations)
            if (!matches(base + rva, bytes.data(), bytes.size())) return false;
        for (const auto& p : patches)
            if (!matches(base + p.rva, install ? p.before.data() : p.after.data(), p.size))
            {
                if (!install) MIF_SHUTDOWN(restore_rejected, p.rva, 0);
                return false;
            }
        if (!install) MIF_SHUTDOWN(bytes_checked, patches.size(), 0);
        std::size_t writable{};
        for (; writable < patches.size(); ++writable)
        {
            const auto& p = patches[writable];
            if (!VirtualProtect(reinterpret_cast<void*>(base + p.rva), p.size, PAGE_EXECUTE_READWRITE,
                                &protections[writable])) break;
        }
        bool ok = writable == patches.size();
        if (!install) MIF_SHUTDOWN(pages_writable, writable, patches.size());
        if (ok)
        {
            for (const auto& p : patches)
                std::memcpy(reinterpret_cast<void*>(base + p.rva), install ? p.after.data() : p.before.data(), p.size);
            if (!install) MIF_SHUTDOWN(bytes_written, patches.size(), 0);
            ok = FlushInstructionCache(GetCurrentProcess(), nullptr, 0) != FALSE;
            if (!install) MIF_SHUTDOWN(cache_flushed, ok, 0);
            if (!ok)
            {
                for (const auto& p : patches)
                    std::memcpy(reinterpret_cast<void*>(base + p.rva), install ? p.before.data() : p.after.data(), p.size);
                FlushInstructionCache(GetCurrentProcess(), nullptr, 0);
                if (!install) MIF_SHUTDOWN(rollback, 0, 0);
            }
        }
        while (writable)
        {
            --writable;
            DWORD ignored{};
            const auto& p = patches[writable];
            if (!VirtualProtect(reinterpret_cast<void*>(base + p.rva), p.size, protections[writable], &ignored))
            {
                // Keep valid callbacks alive even if Windows refuses restoration.
                // Report after threads resume; never free a published trampoline.
                protection_warning = true;
            }
        }
        if (ok) { installed = install; enabled.store(install && stage >= 2, std::memory_order_release); }
        if (!install) MIF_SHUTDOWN(protections_restored, ok, protection_warning);
        return ok;
    }
    bool install()
    {
        if (!validate()) return false;
        bridges.build(stage, evaluation_mode);
        if (stage >= 1 && evaluation_mode == EvaluationMode::Reset)
            add_call(sites::reset_call, bridges.at(0xB00));
        else if (stage >= 1)
        {
            detour = std::make_unique<PreparedDetour>(base + sites::evaluation, reinterpret_cast<std::uintptr_t>(&evaluate_trace), bridges.at(0xA00));
            if (!detour->prepare()) { log("PolyHook could not prepare a seven-byte detour"); return false; }
            if (evaluation_mode == EvaluationMode::Direct)
                bridges.set_evaluation_target(evaluation_trampoline);
            else if (evaluation_mode == EvaluationMode::Trace)
                bridges.set_evaluation_target(reinterpret_cast<std::uintptr_t>(&evaluate_trace));
            diagnostic("[MixedInputFix] Verified: relocated 3+4 bytes; register-preserving JMP to evaluation+7\n");
            add_patch(sites::evaluation, detour->bytes.data(), detour->bytes.size());
        }
        if (stage >= 2) add_indirect_call(sites::winner, bridges.at(0xA08));
        if (stage >= 3) add_indirect_call(sites::dispatch, bridges.at(0xA10));
        if (stage >= 4)
        {
            add_call(sites::getter_x, bridges.at(0x400));
            add_call(sites::getter_y, bridges.at(0x600));
            add_call(sites::movement_getter_b, bridges.at(0xE00));
            add_call(sites::movement_getter_f, bridges.at(0xE00));
            add_call(sites::movement_getter_l, bridges.at(0xC00));
            add_call(sites::movement_getter_r, bridges.at(0xC00));
        }
        if (stage == 4 && evaluation_mode == EvaluationMode::Reset)
        {
            add_call(0x3934757,bridges.at(0x1000));
            add_call(0x4641BC8,bridges.at(0x1200));
            add_call(0x4640A18,bridges.at(0x1300));
            for (const auto [rva,offset] : {std::pair<std::uintptr_t,std::size_t>{0x4641BF5,0x1400},{0x4640A45,0x1500}})
            { add_call(rva,bridges.at(offset)); patches.back().after[0]=0xE9; } // retain tail-JMP contract
            add_indirect_call(0x489D8C9,bridges.at(0x2920));
            add_indirect_call(0x489DB05,bridges.at(0x2928));
            add_indirect_call(0x488A6B9,bridges.at(0x2930));
            add_indirect_call(0x488A8F5,bridges.at(0x2938));
            add_call(0x489DB5C,bridges.at(0x1A00));
            add_call(0x488A94C,bridges.at(0x1A00));
        }
        // Original movement JNEs remain intact. Historical entry diagnostics
        // retain their old NOP behavior only when explicitly selected.
        if (evaluation_mode != EvaluationMode::Reset)
        {
            const std::uint8_t nops[]{0x90, 0x90};
            for (auto rva : sites::movement) add_patch(rva, nops, 2);
        }
        // No future unload may free code while a callback is in flight. Retain the
        // small installation object/trampolines for process lifetime after publish.
        HMODULE self{};
        if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&reset_generation), &self)) return false;
        if (!commit(true)) return false;
        // commit has resumed other threads. A first-execution line may precede
        // these success lines if a game thread immediately enters a new hook.
        if (evaluation_mode != EvaluationMode::Reset)
            diagnostic("[MixedInputFix] Historical diagnostic: four movement NOPs\n");
        if (stage >= 1 && evaluation_mode == EvaluationMode::Reset)
            diagnostic("[MixedInputFix] Installed: reset CALL; persistent generation provenance\n");
        else if (stage >= 1) diagnostic("[MixedInputFix] Installed: evaluation hook\n");
        if (stage >= 2) diagnostic("[MixedInputFix] Installed: winner hook (six-byte indirect CALL)\n");
        if (stage >= 3) diagnostic("[MixedInputFix] Installed: dispatch hook (six-byte indirect CALL)\n");
        if (stage >= 4)
        {
            diagnostic("[MixedInputFix] Installed: horizontal getter redirect\n");
            diagnostic("[MixedInputFix] Installed: vertical getter redirect\n");
            diagnostic("[MixedInputFix] Installed: four provenance-aware movement getters; original branches intact\n");
        }
        return true;
    }
};
Installation* installation{};
}
}

#ifndef MIXED_INPUT_FIX_TEST
class MixedInputFixMod : public RC::CppUserModBase
{
    bool owns_installation{};
public:
    MixedInputFixMod()
    {
        ModName = STR("MixedInputFix");
        ModVersion = STR("2.0");
        ModDescription = STR("Native mouse and stick camera composition and mixed-input movement for Oblivion Remastered.");
        ModAuthors = STR("mamadizzys");
        using namespace mixed_input;
        if (installation) { log("Already initialized; restart the process to reload"); return; }
        open_diagnostics();
#if MIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC
        if (shutdown::open()) diagnostic("[MixedInputFix] Shutdown observer ready: main.dll.shutdown.bin (128 records)\n");
        else diagnostic("[MixedInputFix] Shutdown observer UNAVAILABLE: archive old .shutdown.bin and check directory permissions\n");
#endif
        switch (diagnostic_stage)
        {
        case 0: diagnostic("[MixedInputFix] Diagnostic stage 0 selected\n"); break;
        case 1:
            if (diagnostic_evaluation_mode == EvaluationMode::Direct)
                diagnostic("[MixedInputFix] Diagnostic stage 1A selected: direct trampoline; no runtime entry/return logger\n");
            else if (diagnostic_evaluation_mode == EvaluationMode::Trace)
                diagnostic("[MixedInputFix] Diagnostic stage 1 trace selected: C++ call/return only; no scopes\n");
            else diagnostic("[MixedInputFix] Diagnostic stage 1 selected: reset CALL generation shim\n");
            break;
        case 2: diagnostic("[MixedInputFix] Diagnostic stage 2 selected\n"); break;
        case 3: diagnostic("[MixedInputFix] Diagnostic stage 3 selected\n"); break;
        case 4: diagnostic("[MixedInputFix] Production stage 4 selected: reset CALL/generation; dispatch-only scopes\n"); break;
        }
#if MIXED_INPUT_FIX_DIAGNOSTICS
        if (diagnostic_file == INVALID_HANDLE_VALUE) log("Diagnostic file unavailable; markers use OutputDebugString only");
#endif
        base = reinterpret_cast<std::uintptr_t>(GetModuleHandleW(nullptr));
#if MIXED_INPUT_FIX_CAMERA_PROTOTYPE
        ModName = STR("MixedInputFix Camera Prototype");
        ModVersion = STR("0.1-experimental");
        ModDescription = STR("Experimental native-path additive camera diagnostic.");
        if (!camera_composition::open_journal()) { log("Camera prototype journal unavailable; installation declined"); return; }
        diagnostic("[MixedInputFix] EXPERIMENTAL CAMERA PROTOTYPE: separate native contributions; bounded .camera-PID.bin journal\n");
#endif
        try
        {
            auto pending = std::make_unique<Installation>(diagnostic_stage, diagnostic_evaluation_mode);
            if (!pending->install()) { log("Installation declined; original game code retained"); return; }
            installation = pending.release();
            owns_installation = true;
#if MIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC
            if (shutdown::journal)
            {
                shutdown::journal->bridge = installation->bridges.at(0);
                shutdown::journal->installation = reinterpret_cast<std::uintptr_t>(installation);
            }
#endif
            MIF_SHUTDOWN(installed, installation->patches.size(), 0);
            if (installation->protection_warning) log("Windows refused a page-protection restoration; restart recommended");
        }
        catch (const std::exception& error) { log(error.what()); }
        catch (...) { log("Installation failed"); }
    }
    ~MixedInputFixMod() override
    {
        using namespace mixed_input;
        MIF_SHUTDOWN(destructor_enter, owns_installation, reinterpret_cast<std::uintptr_t>(this));
        if (!owns_installation) return;
        enabled.store(false, std::memory_order_release);
        MIF_SHUTDOWN(overrides_disabled, 0, 0);
        try
        {
            MIF_SHUTDOWN(restore_begin, installation->patches.size(), 0);
            const auto restored = installation->commit(false);
            MIF_SHUTDOWN(commit_result, restored, installation->protection_warning);
            if (!restored) log("Could not restore patches safely; provenance disabled, restart required");
            else log("Original game bytes restored; callback storage retained until process exit");
        }
        catch (...) { MIF_SHUTDOWN(restore_exception, 0, 0); log("Uninstall failed; provenance disabled, restart required"); }
        MIF_SHUTDOWN(destructor_body_end, 0, 0);
    }
};

extern "C"
{
    __declspec(dllexport) RC::CppUserModBase* start_mod() { return new MixedInputFixMod(); }
    __declspec(dllexport) void uninstall_mod(RC::CppUserModBase* mod)
    {
        MIF_SHUTDOWN(uninstall_enter, reinterpret_cast<std::uintptr_t>(mod), reinterpret_cast<std::uintptr_t>(_ReturnAddress()));
        delete mod;
        MIF_SHUTDOWN(uninstall_delete_complete, 0, 0);
    }
}
#endif
