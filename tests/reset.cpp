#define MIXED_INPUT_FIX_TEST
#include "../src/dllmain.cpp"
#include <cassert>
#include <cstddef>
#include <limits>
using namespace mixed_input;
using namespace asmjit::x86;
namespace
{
template <typename T> void put(std::uintptr_t address, const T& value)
{ std::memcpy(reinterpret_cast<void*>(address), &value, sizeof(value)); }
void copy_code(asmjit::CodeHolder& code, std::uintptr_t address)
{
    check(code.flatten()); check(code.resolveUnresolvedLinks()); check(code.relocateToBase(address));
    check(code.copyFlattenedData(reinterpret_cast<void*>(address), code.codeSize()));
}
void protect_code(std::uintptr_t address)
{
    DWORD old{};
    assert(VirtualProtect(reinterpret_cast<void*>(address), 0x1000, PAGE_EXECUTE_READ, &old));
    assert(FlushInstructionCache(GetCurrentProcess(), nullptr, 0));
}
struct alignas(16) Snapshot
{
    std::uint64_t gpr[16]{}, flags{}, return_address{}, stack[6]{};
    alignas(16) std::array<std::uint8_t, 512> fx{};
    std::uint64_t returned_rax{}, returned_flags{}, caller_stack[6]{};
    alignas(16) std::array<std::uint8_t, 16> returned_xmm{};
};
std::array<std::uint8_t, 0x100> action{}, instance{}, common{}, mapping{};
int owner{}, other_owner{}, executions{};
std::uint64_t original_calls{};
std::uintptr_t active_frame{};
void camera(void*, void*) { ++executions; assert(input_x(common.data()) == 0); }
void vanilla_camera(void*, void*) { ++executions; assert(input_x(common.data()) == common[0x91]); }
void nested_camera(void*, void*)
{
    assert(input_x(common.data()) == 0);
    Execute table[]{nullptr, &vanilla_camera}; auto* binding = table;
    dispatch(&binding, instance.data(), &other_owner, active_frame);
    assert(input_x(common.data()) == 0); // Mismatched dispatch masks, then restores.
    reset_generation(&owner, active_frame - 0x1000, active_frame - 0x1108);
    assert(input_x(common.data()) == common[0x91]); // Nested reset invalidates outer.
}
Installation* pending_uninstall{};
void uninstall_from_reset()
{
    assert(pending_uninstall->commit(false));
}
}
int main()
{
    open_diagnostics();
    base = reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr, 0x9120000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(base);
    IMAGE_DOS_HEADER dos{}; dos.e_magic = IMAGE_DOS_SIGNATURE; dos.e_lfanew = 0x100; put(base, dos);
    IMAGE_NT_HEADERS64 nt{}; nt.Signature = IMAGE_NT_SIGNATURE; nt.FileHeader.Machine = IMAGE_FILE_MACHINE_AMD64;
    nt.OptionalHeader.Magic = IMAGE_NT_OPTIONAL_HDR64_MAGIC; nt.OptionalHeader.SizeOfImage = 0x9120000; put(base + 0x100, nt);
    for (const auto& signature : sites::signatures)
    {
        const auto bytes = decode(signature.hex);
        std::memcpy(reinterpret_cast<void*>(base + signature.rva), bytes.data(), bytes.size());
    }
    for (const auto& sig : camera_composition::signatures)
    {
        const auto bytes = decode(sig.hex);
        std::memcpy(reinterpret_cast<void*>(base + sig.rva), bytes.data(), bytes.size());
    }
    asmjit::JitRuntime runtime;
    // The original CALL displacement and newly relied-on owner setup are both
    // guarded by the full preflight signatures before any bridge is published.
    for (auto rva : {sites::reset_call + 1, std::uintptr_t{0x392B660}})
    {
        auto& byte = *reinterpret_cast<std::uint8_t*>(base + rva);
        byte ^= 1;
        Installation declined(4);
        assert(!declined.install() && declined.patches.empty() && !declined.bridges.memory);
        byte ^= 1;
    }
    Installation install(4);
    assert(install.install() && install.patches.size() == 20 && !install.detour);
    auto& bridges = install.bridges;
    assert(bridges.reset_registered && bridges.registered);
    std::uintptr_t entry_target{1};
    assert(read(bridges.at(0xA00), entry_target) && entry_target == 0);
    assert(install.patches[0].rva == sites::reset_call && install.patches[0].size == 5);
    assert(install.patches[0].before[0] == 0xE8 && install.patches[0].after[0] == 0xE8);
    for (const auto& signature : sites::signatures)
        if (signature.rva == sites::evaluation)
        {
            const auto bytes = decode(signature.hex);
            assert(matches(base + signature.rva, bytes.data(), bytes.size()));
        }
    for (auto rva : {sites::getter_x, sites::getter_y})
    {
        const std::uint8_t cmp[]{0x3C, 1}; assert(matches(base + rva + 5, cmp, 2));
    }

    // Synthetic original reset snapshots all GPRs, flags, x87/XMM/MXCSR, return
    // address and incoming home/stack slots before modifying any of that state.
    asmjit::CodeHolder original; check(original.init(runtime.environment(), base + sites::reset_original));
    Assembler b(&original);
    const Gp regs[]{rax, rcx, rdx, rbx, rsp, rbp, rsi, rdi, r8, r9, r10, r11, r12, r13, r14, r15};
    for (int i = 0; i < 16; ++i) b.mov(qword_ptr(r12, offsetof(Snapshot, gpr) + i * 8), regs[i]);
    b.pushfq(); b.pop(qword_ptr(r12, offsetof(Snapshot, flags)));
    b.fxsave64(ptr(r12, offsetof(Snapshot, fx)));
    b.mov(r11, qword_ptr(rsp)); b.mov(qword_ptr(r12, offsetof(Snapshot, return_address)), r11);
    for (int i = 0; i < 6; ++i)
    {
        b.mov(r11, qword_ptr(rsp, 8 + i * 8)); b.mov(qword_ptr(r12, offsetof(Snapshot, stack) + i * 8), r11);
    }
    b.pushfq(); b.mov(r11, reinterpret_cast<std::uintptr_t>(&original_calls)); b.inc(qword_ptr(r11)); b.popfq();
    b.mov(rax, 0x1234567887654321ULL); b.movdqa(xmm0, xmm5); b.stc(); b.ret();
    copy_code(original, base + sites::reset_original); protect_code(base + sites::reset_original);

    // A single caller/CALL instruction is reused for direct, shimmed and stress
    // shimmed calls, so the expected original return address and frame are exact.
    alignas(16) std::uint64_t vector[]{0x1122334455667788ULL, 0x8877665544332211ULL};
    const std::uint32_t mxcsr = 0x3FA0; // Different rounding, sticky precision flag.
    asmjit::CodeHolder caller; check(caller.init(runtime.environment())); Assembler a(&caller);
    for (auto reg : {rbx, rbp, rsi, rdi, r12, r13, r14, r15}) a.push(reg);
    a.sub(rsp, 0x268); a.fxsave64(ptr(rsp, 0x60));
    a.mov(rbx, rcx); a.mov(r12, rdx); a.mov(r13, reinterpret_cast<std::uintptr_t>(&owner));
    a.lea(rbp, ptr(rsp, 0x100));
    for (int i = 0; i < 6; ++i) a.mov(qword_ptr(rsp, i * 8), 0x12340000 + i);
    a.fninit(); a.fld1();
    a.mov(rax, reinterpret_cast<std::uintptr_t>(&mxcsr)); a.ldmxcsr(dword_ptr(rax));
    a.mov(rax, reinterpret_cast<std::uintptr_t>(vector));
    for (int i = 0; i < 16; ++i) a.movdqu(xmm(i), ptr(rax));
    for (auto reg : {rax, rcx, rdx, rsi, rdi, r8, r9, r10, r11, r14, r15})
        a.mov(reg, 0xAABBCCDD00000000ULL + reg.id());
    a.cmp(rax, rax); a.stc(); a.std(); // Restore DF before returning to C++ below.
    a.call(rbx);
    a.mov(qword_ptr(r12, offsetof(Snapshot, returned_rax)), rax);
    a.pushfq(); a.pop(qword_ptr(r12, offsetof(Snapshot, returned_flags)));
    a.movdqu(ptr(r12, offsetof(Snapshot, returned_xmm)), xmm0);
    for (int i = 0; i < 6; ++i)
    {
        a.mov(r11, qword_ptr(rsp, i * 8)); a.mov(qword_ptr(r12, offsetof(Snapshot, caller_stack) + i * 8), r11);
    }
    a.cld(); a.fxrstor64(ptr(rsp, 0x60)); a.add(rsp, 0x268);
    for (auto reg : {r15, r14, r13, r12, rdi, rsi, rbp, rbx}) a.pop(reg);
    a.ret();
    using Invoke = void (*)(std::uintptr_t, Snapshot*);
    Invoke invoke{}; check(runtime.add(&invoke, &caller));

    // Stress helper keeps the real bounded reset, then deliberately destroys
    // ABI-volatile GPR/XMM, x87 and MXCSR state to test the shim's restores.
    asmjit::CodeHolder stress; check(stress.init(runtime.environment())); Assembler c(&stress);
    c.sub(rsp, 0x28); c.mov(rax, reinterpret_cast<std::uintptr_t>(&reset_generation)); c.call(rax);
    c.fninit(); c.fldz(); c.mov(dword_ptr(rsp, 0x20), 0x1F80); c.ldmxcsr(dword_ptr(rsp, 0x20));
    for (int i = 0; i < 6; ++i) c.pxor(xmm(i), xmm(i));
    for (auto reg : {rax, rcx, rdx, r8, r9, r10, r11}) c.xor_(reg, reg);
    c.add(rsp, 0x28); c.clc(); c.ret();
    void (*stress_helper)(){}; check(runtime.add(&stress_helper, &stress));
    // Replace only the generated helper immediate in this isolated synthetic test page;
    // production build always embeds &reset_generation directly.
    std::size_t helper_offset{}; int helper_matches{};
    const auto helper = reinterpret_cast<std::uintptr_t>(&reset_generation);
    for (std::size_t i = 0; i + 8 <= bridges.reset_size; ++i)
        if (!std::memcmp(bridges.memory + 0xB00 + i, &helper, 8)) { helper_offset = i; ++helper_matches; }
    assert(helper_matches == 1);
    Snapshot snapshot{}, expected{};
    for (int pass = 0; pass < 3; ++pass)
    {
        if (pass == 2)
        {
            DWORD old{}; assert(VirtualProtect(bridges.memory, bridges.size, PAGE_READWRITE, &old));
            put(bridges.at(0xB00 + helper_offset), reinterpret_cast<std::uintptr_t>(stress_helper));
            protect_code(bridges.at(0));
        }
        snapshot = {};
        invoke(pass == 0 ? base + sites::reset_original : bridges.at(0xB00), &snapshot);
        assert(original_calls == unsigned(pass + 1));
        // The caller deliberately retains its target in RBX; that one value
        // differs between direct/shim selection and is separately checked.
        assert(snapshot.gpr[3] == (pass == 0 ? base + sites::reset_original : bridges.at(0xB00)));
        snapshot.gpr[3] = 0;
        if (pass == 0) expected = snapshot;
        else assert(!std::memcmp(&snapshot, &expected, sizeof(snapshot)));
        for (int i = 0; i < 6; ++i)
            assert(snapshot.stack[i] == 0x12340000U + i && snapshot.caller_stack[i] == snapshot.stack[i]);
        assert(snapshot.returned_rax == 0x1234567887654321ULL);
        if (pass)
        {
            assert(provenance.valid && provenance.generation.owner == &owner);
            assert(provenance.generation.frame == snapshot.gpr[5] && provenance.generation.number == unsigned(pass));
        }
    }
    DWORD old{}; assert(VirtualProtect(bridges.memory, bridges.size, PAGE_READWRITE, &old));
    put(bridges.at(0xB00 + helper_offset), helper); protect_code(bridges.at(0));
    // Dump the actual AsmJit shim for review with the production helper restored.
    FILE* dump{}; assert(fopen_s(&dump, "build/reset-shim.bin", "wb") == 0);
    assert(fwrite(bridges.memory + 0xB00, 1, bridges.reset_size + 8, dump) == bridges.reset_size + 8); fclose(dump);
    std::printf("Reset shim: %llX, helper: %llX, original: %llX; body=%zu popfq=%zu tail=%zu size=%zu\n",
        static_cast<unsigned long long>(bridges.at(0xB00)), static_cast<unsigned long long>(helper),
        static_cast<unsigned long long>(base + sites::reset_original), bridges.reset_body, bridges.reset_pop_flags, bridges.reset_tail, bridges.reset_size);
    std::puts("PASS: reset shim exact GPR/RFLAGS/x87/XMM0-15/MXCSR/RSP/return/stack comparison, stress clobbers, original called once per invocation");

    // Asynchronous unwind at every instruction boundary in the shim, including
    // PUSHFQ/SUB prologue, POPFQ, and the register-preserving final tail jump.
    alignas(16) std::uint64_t stack[100]{};
    const auto top = reinterpret_cast<DWORD64>(stack + 90);
    constexpr DWORD64 return_pc = 0x123456789;
    put(top, return_pc);
    ZydisDecoder decoder; ZydisDecoderInit(&decoder, ZYDIS_MACHINE_MODE_LONG_64, ZYDIS_STACK_WIDTH_64);
    for (std::size_t offset = 0; offset < bridges.reset_size;)
    {
        ZydisDecodedInstruction instruction{};
        assert(ZYAN_SUCCESS(ZydisDecoderDecodeInstruction(&decoder, nullptr, bridges.memory + 0xB00 + offset,
            bridges.reset_size - offset, &instruction)));
        CONTEXT ctx{}; ctx.Rip = bridges.at(0xB00 + offset);
        ctx.Rsp = offset == 0 || offset >= bridges.reset_tail ? top :
            (offset == 1 || offset >= bridges.reset_pop_flags ? top - 8 : top - 0x268);
        auto* function = &bridges.reset_unwind[offset < bridges.reset_pop_flags ? 0 : offset < bridges.reset_tail ? 1 : 2];
        void* data{}; DWORD64 frame{};
        RtlVirtualUnwind(0, bridges.at(0), ctx.Rip, function, &ctx, &data, &frame, nullptr);
        assert(ctx.Rip == return_pc && ctx.Rsp == top + 8);
        offset += instruction.length;
    }
    std::puts("PASS: reset dynamic unwind at every emitted instruction boundary");

    // Execute the installed real reset CALL site and return to its original +5,
    // including restoring that CALL while the original reset is still running.
    // A synthetic stub uses the game's frame relation, then jumps to the CALL.
    asmjit::CodeHolder site_caller; check(site_caller.init(runtime.environment(), base + 0x4000)); Assembler d(&site_caller);
    d.push(rbp); d.push(r13); d.sub(rsp, 0x128); d.lea(rbp, ptr(rsp, 0x100));
    d.mov(r13, reinterpret_cast<std::uintptr_t>(&owner)); d.jmp(asmjit::imm(base + sites::reset_call));
    copy_code(site_caller, base + 0x4000); protect_code(base + 0x4000);
    asmjit::CodeHolder continuation; check(continuation.init(runtime.environment(), base + sites::reset_call + 5)); Assembler f(&continuation);
    f.add(rsp, 0x128); f.pop(r13); f.pop(rbp); f.ret();
    assert(VirtualProtect(reinterpret_cast<void*>(base + sites::reset_call), 0x1000, PAGE_READWRITE, &old));
    copy_code(continuation, base + sites::reset_call + 5); protect_code(base + sites::reset_call);
    asmjit::CodeHolder unhook; check(unhook.init(runtime.environment(), base + sites::reset_original)); Assembler u(&unhook);
    u.sub(rsp, 0x28); u.mov(rax, reinterpret_cast<std::uintptr_t>(&uninstall_from_reset)); u.call(rax); u.add(rsp, 0x28); u.ret();
    assert(VirtualProtect(reinterpret_cast<void*>(base + sites::reset_original), 0x1000, PAGE_READWRITE, &old));
    copy_code(unhook, base + sites::reset_original); protect_code(base + sites::reset_original);
    pending_uninstall = &install;
    const auto generation_before = provenance.generation.number;
    reinterpret_cast<void (*)()>(base + 0x4000)();
    assert(!install.installed && !enabled.load() && provenance.generation.number == generation_before + 1 && provenance.valid);
    assert(install.validate());
    std::puts("PASS: actual reset CALL install/execute/in-flight restore returns at original +5; 20 patches restored, evaluation entry and camera comparisons intact");

    // Integration gates use the actual recorder, dispatch wrapper and getter.
    protect_code(base + sites::getter);
    active_frame = 0x200000;
    reset_generation(&owner, active_frame, active_frame - 0x108);
    const auto token = provenance.generation;
    enabled = true;
    put(reinterpret_cast<std::uintptr_t>(instance.data()), action.data()); instance[0x50] = 1;
    const auto frame = reinterpret_cast<std::uintptr_t>(mapping.data()) + 0x70;
    put(frame + 0x37, active_frame); put(frame + 0x3F, base + sites::mapping_return); put(frame + 0x4F, action.data());
    const std::uint64_t keys[]{0x12340001, 0x12340002, 0x12340003, 0x12340004};
    for (auto [rva, key_value] : {std::pair{sites::mouse_x, keys[0]}, {sites::mouse_y, keys[1]}, {sites::gamepad_x, keys[2]}, {sites::gamepad_y, keys[3]}}) put(base + rva, key_value);
    std::uint64_t key = keys[0]; put(frame + 0x1F, &key);
    record_winner(frame, &owner, instance.data(), 0);
    assert(provenance.lookup(token, action.data(), instance.data()).source == Source::Mouse);
    common[0x91] = 1;
    assert(input_x(common.data()) == 1); // Persistent record alone cannot override.
    Execute table[]{nullptr, &camera}; auto* binding = table;
    dispatch(&binding, instance.data(), &owner, active_frame); assert(executions == 1 && !current_dispatch);
    key = keys[2]; record_winner(frame, &owner, instance.data(), 0);
    assert(provenance.lookup(token, action.data(), instance.data()).source == Source::Gamepad);
    key = 0xFFFFFFFF; record_winner(frame, &owner, instance.data(), 0);
    table[1] = &vanilla_camera; dispatch(&binding, instance.data(), &owner, active_frame);
    key = keys[0]; record_winner(frame, &owner, instance.data(), 0);
    put(frame + 0x3F, std::uintptr_t{0}); record_winner(frame, &owner, instance.data(), 0);
    dispatch(&binding, instance.data(), &owner, active_frame); // Foreign caller erased Mouse.
    put(frame + 0x3F, base + sites::mapping_return); record_winner(frame, &owner, instance.data(), 0);
    table[1] = &vanilla_camera;
    dispatch(&binding, instance.data(), &owner, active_frame + 0x1000); // Wrong frame.
    {
        Dispatch stale{token, action.data(), instance.data(), {Source::Mouse, Axis::X}};
        Scope scope(current_dispatch, &stale);
        action[0x51] = 1; assert(input_x(common.data()) == 1); action[0x51] = 0;
        instance[0x50] = 2; assert(input_x(common.data()) == 1); instance[0x50] = 1;
        std::array<std::uint8_t, 0x100> other_action{};
        put(reinterpret_cast<std::uintptr_t>(instance.data()), other_action.data());
        assert(input_x(common.data()) == 1);
        put(reinterpret_cast<std::uintptr_t>(instance.data()), action.data());
        reset_generation(&owner, active_frame, active_frame - 0x108);
        record_winner(frame, &owner, instance.data(), 0);
        assert(input_x(common.data()) == 1); // Same owner/frame/action, stale generation.
    }
    table[1] = &nested_camera; dispatch(&binding, instance.data(), &owner, active_frame);
    assert(!current_dispatch && !provenance.matches(token));
    record_winner(frame, &owner, instance.data(), 0); assert(!provenance.valid); // Resumed outer.
    reset_generation(&owner, active_frame, active_frame - 0x108);
    record_winner(frame, &other_owner, instance.data(), 0); assert(!provenance.valid);
    reset_generation(&owner, active_frame, 0); assert(!provenance.valid); // Bad reset frame.
    provenance.generation.number = std::numeric_limits<std::uint64_t>::max();
    reset_generation(&owner, active_frame, active_frame - 0x108); assert(!provenance.valid && provenance.exhausted);
    std::puts("PASS: actual recorder owner/frame gates, replacement/Unknown/foreign invalidation, getter outside dispatch, nested dispatch masking and evaluation invalidation, bad reset frame and rollover fallback");
    runtime.release(invoke); runtime.release(stress_helper);
}
