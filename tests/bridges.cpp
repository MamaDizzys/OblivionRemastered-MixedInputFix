#define MIXED_INPUT_FIX_TEST
#include "../src/dllmain.cpp"
#include <cassert>
#include <bit>
using namespace mixed_input;
using namespace asmjit::x86;
namespace
{
int callbacks{};
std::uint8_t observed{};
std::array<std::uint8_t, 0x100> common{};
Installation* in_flight_installation{};
constexpr std::uintptr_t evaluation_frame = 0x200000;
void uninstall_during_dispatch(void*, void*)
{
    assert(current_dispatch);
    assert(in_flight_installation->commit(false));
    ++callbacks;
}
void camera(void*, void*) { ++callbacks; observed = input_x(common.data()); }
void throwing_camera(void*, void*) { throw std::runtime_error("dispatch unwind"); }
void seh_camera(void*, void*) { RaiseException(0xE0421234, 0, 0, nullptr); }
bool seh_dispatch(void* record, void* owner)
{
    __try {
        Execute vtable[]{nullptr, &seh_camera};
        auto* binding = vtable;
        dispatch(&binding, record, owner, evaluation_frame);
    }
    __except (GetExceptionCode() == 0xE0421234 ? EXCEPTION_EXECUTE_HANDLER : EXCEPTION_CONTINUE_SEARCH) { return true; }
    return false;
}
template <typename T> void put(std::uintptr_t where, T value) { std::memcpy(reinterpret_cast<void*>(where), &value, sizeof(value)); }
}
int main()
{
    open_diagnostics();
#if MIXED_INPUT_FIX_DIAGNOSTICS
    assert(diagnostic_file != INVALID_HANDLE_VALUE);
#else
    // Normal production leaves diagnostic file creation and markers inactive.
    assert(diagnostic_file == INVALID_HANDLE_VALUE);
#endif
    std::atomic_flag marker{};
    SetLastError(0x1234);
    first_execution(marker, "[MixedInputFix] Test: once-only diagnostic\n");
    first_execution(marker, "[MixedInputFix] Test: once-only diagnostic\n");
    assert(GetLastError() == 0x1234);
#if !MIXED_INPUT_FIX_DIAGNOSTICS
    assert(!marker.test());
#endif
    base = reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr, 0x9120000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(base);
    IMAGE_DOS_HEADER dos{};
    dos.e_magic = IMAGE_DOS_SIGNATURE;
    dos.e_lfanew = 0x100;
    put(base, dos);
    IMAGE_NT_HEADERS64 nt{};
    nt.Signature = IMAGE_NT_SIGNATURE;
    nt.FileHeader.Machine = IMAGE_FILE_MACHINE_AMD64;
    nt.OptionalHeader.Magic = IMAGE_NT_OPTIONAL_HDR64_MAGIC;
    nt.OptionalHeader.SizeOfImage = 0x9120000;
    put(base + 0x100, nt);
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
    Installation transaction;
    assert(transaction.validate());
    *reinterpret_cast<std::uint8_t*>(base + sites::getter_x + 6) = 0xFF;
    assert(!transaction.validate());
    *reinterpret_cast<std::uint8_t*>(base + sites::getter_x + 6) = 1;
    assert(transaction.validate());
    const std::uint64_t keys[] = {0x123400001005, 0x123400001006, 0x123400001007, 0x123400001008};
    put(base + sites::mouse_x, keys[0]); put(base + sites::mouse_y, keys[1]);
    put(base + sites::gamepad_x, keys[2]); put(base + sites::gamepad_y, keys[3]);
    std::array<std::uint8_t, 0x100> action{}, instance{}, frame_storage{};
    int owner{};
    const auto action_ptr = reinterpret_cast<std::uintptr_t>(action.data());
    put(reinterpret_cast<std::uintptr_t>(instance.data()), action.data());
    instance[0x50] = 1;
    const auto frame = reinterpret_cast<std::uintptr_t>(frame_storage.data()) + 0x70;
    std::uint64_t key = keys[0];
    put(frame + 0x1F, &key);
    put(frame + 0x3F, base + sites::mapping_return);
    put(frame + 0x4F, action_ptr);
    DWORD old{};
    assert(VirtualProtect(reinterpret_cast<void*>(base + sites::getter), 16, PAGE_EXECUTE_READ, &old));
    Bridges bridges;
    bridges.build(4); // Always retain production bridge coverage, irrespective of DLL stage.
    auto& evaluation = provenance;
    evaluation.reset(&owner, evaluation_frame);
    put(frame + 0x37, evaluation_frame);
    enabled = true;

    // Exercise the actual AsmJit winner bridge, including CF, GPR and XMM restore.
    asmjit::JitRuntime runtime;
    asmjit::CodeHolder code;
    check(code.init(runtime.environment()));
    AsmErrors errors;
    code.setErrorHandler(&errors);
    Assembler a(&code);
    a.push(rbp); a.push(rdi); a.push(r14);
    a.sub(rsp, 0x20);
    a.mov(rbp, rcx); a.mov(r14, rdx); a.mov(rdi, r8); a.xor_(ecx, ecx);
    a.mov(r8, 0x11223344); a.mov(r10, 0x55667788);
    a.mov(rax, std::bit_cast<std::uint64_t>(10.36)); a.movq(xmm2, rax);
    a.mov(rax, bridges.at(0)); a.stc(); a.call(rax);
    a.pushfq(); a.pop(rax); a.and_(eax, 1);
    const auto fail = a.newLabel(), done = a.newLabel();
    a.cmp(rcx, 0); a.jne(fail);
    a.cmp(r8, 0x11223344); a.jne(fail);
    a.cmp(r10, 0x55667788); a.jne(fail);
    a.jmp(done); a.bind(fail); a.xor_(eax, eax); a.bind(done);
    a.add(rsp, 0x20); a.pop(r14); a.pop(rdi); a.pop(rbp); a.ret();
    using Invoke = std::uint64_t (*)(std::uintptr_t, void*, void*);
    Invoke invoke{};
    check(runtime.add(&invoke, &code));
    assert(invoke(frame, &owner, instance.data()) == 1);
    double stored{};
    assert(read(frame - 0x69, stored) && stored == 10.36);
    assert(evaluation.lookup(evaluation.generation, action.data(), instance.data()).source == Source::Mouse);
    key = keys[2];
    assert(invoke(frame, &owner, instance.data()) == 1);
    assert(evaluation.lookup(evaluation.generation, action.data(), instance.data()).source == Source::Gamepad);
    key = 0xFFFFFFFF;
    invoke(frame, &owner, instance.data());
    assert(evaluation.lookup(evaluation.generation, action.data(), instance.data()).source == Source::Unknown);
    key = keys[0];
    invoke(frame, &owner, instance.data());
    put(frame + 0x3F, std::uintptr_t{});
    invoke(frame, &owner, instance.data());
    assert(evaluation.lookup(evaluation.generation, action.data(), instance.data()).source == Source::Unknown);
    put(frame + 0x3F, base + sites::mapping_return);
    invoke(frame, &owner, instance.data());

    // Verify dynamic unwind metadata at a point inside the non-leaf bridge.
    alignas(16) std::uint64_t stack[40]{};
    const auto sp = reinterpret_cast<DWORD64>(stack);
    stack[0xC8 / 8] = 0x123456789;
    CONTEXT context{};
    context.Rip = bridges.at(0x20); context.Rsp = sp;
    void* handler_data{}; DWORD64 establisher{};
    RtlVirtualUnwind(0, bridges.at(0), context.Rip, &bridges.unwind[0], &context,
                     &handler_data, &establisher, nullptr);
    assert(context.Rip == 0x123456789 && context.Rsp == sp + 0xD0);
    for (std::size_t i = 1; i < bridges.unwind.size(); ++i)
    {
        context.Rip = bridges.at(bridges.unwind[i].BeginAddress);
        context.Rsp = sp + (i == 1 ? 0xC0 : 0xC8);
        RtlVirtualUnwind(0, bridges.at(0), context.Rip, &bridges.unwind[i], &context,
                         &handler_data, &establisher, nullptr);
        assert(context.Rip == 0x123456789 && context.Rsp == sp + 0xD0);
    }

    // Call the actual dispatch adapter through a synthetic caller supplying R13.
    asmjit::CodeHolder dispatch_code;
    check(dispatch_code.init(runtime.environment()));
    Assembler d(&dispatch_code);
    d.push(rbp); d.push(r13); d.sub(rsp, 0x28); d.mov(r13, r8); d.mov(rbp, r9);
    d.mov(rax, bridges.at(0x200)); d.call(rax);
    d.add(rsp, 0x28); d.pop(r13); d.pop(rbp); d.ret();
    using DispatchInvoke = void (*)(void*, void*, void*, std::uintptr_t);
    DispatchInvoke dispatch_invoke{};
    check(runtime.add(&dispatch_invoke, &dispatch_code));
    void* vtable[]{nullptr, reinterpret_cast<void*>(&camera)};
    void* binding = vtable;
    common[0x91] = 1;
    dispatch_invoke(&binding, instance.data(), &owner, evaluation_frame);
    assert(callbacks == 1 && observed == 0 && current_dispatch == nullptr);
    key = keys[2]; invoke(frame, &owner, instance.data());
    common[0x91] = 0;
    dispatch_invoke(&binding, instance.data(), &owner, evaluation_frame);
    assert(callbacks == 2 && observed == 1);
    action[0x51] = 1;
    dispatch_invoke(&binding, instance.data(), &owner, evaluation_frame);
    assert(callbacks == 3 && observed == 0); // Additive policy falls back.
    action[0x51] = 0;
    key = keys[1]; invoke(frame, &owner, instance.data());
    dispatch_invoke(&binding, instance.data(), &owner, evaluation_frame);
    assert(callbacks == 4 && observed == 0); // Wrong axis falls back.
    vtable[1] = reinterpret_cast<void*>(&throwing_camera);
    try { dispatch(&binding, instance.data(), &owner, evaluation_frame); assert(false); }
    catch (const std::runtime_error&) {}
    assert(current_dispatch == nullptr);
    assert(seh_dispatch(instance.data(), &owner));
    assert(current_dispatch == nullptr);

    const std::uint8_t nops[]{0x90, 0x90};
    transaction.add_patch(sites::movement[0], nops, 2);
    *reinterpret_cast<std::uint8_t*>(base + sites::getter_x + 6) = 0xFF;
    assert(!transaction.commit(true)); // Late conflicting mod: no movement write.
    assert(matches(base + sites::movement[0], transaction.patches[0].before.data(), 2));
    *reinterpret_cast<std::uint8_t*>(base + sites::getter_x + 6) = 1;
    assert(transaction.commit(true));
    assert(matches(base + sites::movement[0], nops, 2));
    assert(transaction.commit(false));
    assert(transaction.validate());
    for (unsigned stage = 0; stage <= 4; ++stage)
    {
        Installation staged(stage);
        assert(staged.install());
        assert(staged.patches.size() == stage + (stage == 4 ? 16 : 0));
        assert(!staged.detour);
        assert(staged.bridges.reset_registered == (stage >= 1));
        assert(bool(staged.bridges.memory) == (stage >= 1));
        assert(staged.bridges.registered == (stage >= 2));
        assert(enabled.load() == (stage >= 2));
        for (const auto& patch : staged.patches)
        {
            assert(matches(base + patch.rva, patch.after.data(), patch.size));
            if (patch.rva == sites::winner || patch.rva == sites::dispatch)
                assert(patch.size == 6 && patch.after[0] == 0xFF && patch.after[1] == 0x15);
        }
        const std::uint8_t camera_cmp[]{0x3C, 1};
        assert(matches(base + sites::getter_x + 5, camera_cmp, 2));
        assert(matches(base + sites::getter_y + 5, camera_cmp, 2));
        const std::uint8_t movement_branches[]{0x75, 0x0F};
        for (auto rva : sites::movement) assert(matches(base + rva, movement_branches, 2));
        // Only the intended hook sites may appear in each stage's patch set.
        for (auto [rva, minimum] : {std::pair{sites::reset_call, 1U}, {sites::winner, 2U},
             {sites::dispatch, 3U}, {sites::getter_x, 4U}, {sites::getter_y, 4U}})
        {
            bool patched = false;
            for (const auto& patch : staged.patches) patched |= patch.rva == rva;
            assert(patched == (stage >= minimum));
        }
        if (stage == 1)
        {
            std::uintptr_t winner_slot{1}, dispatch_slot{1};
            assert(read(staged.bridges.at(0xA08), winner_slot) && winner_slot == 0);
            assert(read(staged.bridges.at(0xA10), dispatch_slot) && dispatch_slot == 0);
        }
        assert(staged.commit(false));
        assert(staged.validate());
        assert(!enabled.load());
    }

    // Reproduce uninstall while a dispatch callback is in flight. The caller
    // must return after the restored six-byte sequence, never into its last byte.
    // A real binding may still be executing when another thread uninstalls;
    // restoring from the binding itself exercises the same pending return address.
    constexpr std::uintptr_t regression_rva = 0x3000;
    asmjit::CodeHolder regression_code;
    check(regression_code.init(runtime.environment(), base + regression_rva));
    Assembler regression(&regression_code);
    regression.push(rbp); regression.push(r13); regression.sub(rsp, 0x28); regression.mov(r13, r8); regression.mov(rbp, r9);
    const auto call_offset = regression.offset();
    regression.mov(rax, qword_ptr(rcx)); regression.call(qword_ptr(rax, 8));
    assert(regression.offset() == call_offset + 6);
    regression.add(rsp, 0x28); regression.pop(r13); regression.pop(rbp); regression.ret();
    check(regression_code.flatten());
    check(regression_code.resolveUnresolvedLinks());
    check(regression_code.relocateToBase(base + regression_rva));
    check(regression_code.copyFlattenedData(reinterpret_cast<void*>(base + regression_rva), regression_code.codeSize()));
    assert(VirtualProtect(reinterpret_cast<void*>(base + regression_rva), 0x1000, PAGE_EXECUTE_READ, &old));
    assert(FlushInstructionCache(GetCurrentProcess(), reinterpret_cast<void*>(base + regression_rva), regression_code.codeSize()));
    Installation in_flight;
    in_flight.add_indirect_call(regression_rva + call_offset, bridges.at(0xA10));
    in_flight_installation = &in_flight;
    assert(in_flight.commit(true));
    vtable[1] = reinterpret_cast<void*>(&uninstall_during_dispatch);
    const auto before_calls = callbacks;
    reinterpret_cast<DispatchInvoke>(base + regression_rva)(&binding, instance.data(), &owner, evaluation_frame);
    assert(callbacks == before_calls + 1 && current_dispatch == nullptr && !in_flight.installed);
    assert(matches(base + regression_rva + call_offset, in_flight.patches[0].before.data(), 6));
    runtime.release(invoke); runtime.release(dispatch_invoke);
    std::puts("PASS: signatures, winner bridge/registers/store, dynamic unwind, dispatch once, getter fallback, additive, C++/SEH scopes, reset CALL stage sets, stages 0-4, commit/restore, in-flight unhook return");
}
