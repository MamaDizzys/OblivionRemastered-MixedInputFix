#define MIXED_INPUT_FIX_TEST
#include "../src/dllmain.cpp"
#include <cassert>
#include <cstddef>
using namespace mixed_input;
using namespace asmjit::x86;

namespace
{
struct Snapshot
{
    std::uint64_t entry_rsp{}, body_rsp{}, return_address{}, gpr[7]{}, fifth{}, sixth{};
    std::uint64_t work_data{}, caller_fifth{}, caller_sixth{};
    std::uint32_t work_num{}, work_max{};
    std::uint64_t home_rcx{}, home_rdx{}, home_paused{}, flags{};
    std::array<std::array<std::uint8_t, 16>, 6> xmm{};
    std::uint64_t returned_rax{}, returned_flags{};
    std::array<std::uint8_t, 16> returned_xmm{};
};
// Synthetic header only; the engine's precise C++ work-list type is unknown.
struct WorkList { void* data; std::uint32_t num, max; };
static_assert(offsetof(WorkList, num) == 8 && offsetof(WorkList, max) == 12);
template <typename T> void put(std::uintptr_t address, const T& value)
{ std::memcpy(reinterpret_cast<void*>(address), &value, sizeof(value)); }
void copy_code(asmjit::CodeHolder& code, std::uintptr_t address)
{
    check(code.flatten()); check(code.resolveUnresolvedLinks()); check(code.relocateToBase(address));
    check(code.copyFlattenedData(reinterpret_cast<void*>(address), code.codeSize()));
}
void dump_trampoline()
{
    std::int32_t displacement{};
    assert(read(evaluation_trampoline + 9, displacement));
    const auto slot = evaluation_trampoline + 13 + displacement;
    std::uintptr_t continuation{};
    assert(read(slot, continuation));
    assert(continuation == base + sites::evaluation + 7);
    std::printf("Trampoline %llX:", static_cast<unsigned long long>(evaluation_trampoline));
    for (int i = 0; i < 13; ++i)
        std::printf(" %02X", reinterpret_cast<const std::uint8_t*>(evaluation_trampoline)[i]);
    std::printf("\nJump slot %llX -> %llX (expected %llX)\n",
        static_cast<unsigned long long>(slot), static_cast<unsigned long long>(continuation),
        static_cast<unsigned long long>(base + sites::evaluation + 7));
}
}

int main()
{
    open_diagnostics();
#if MIXED_INPUT_FIX_DIAGNOSTICS
    assert(diagnostic_file != INVALID_HANDLE_VALUE);
#else
    assert(diagnostic_file == INVALID_HANDLE_VALUE);
#endif
    base = reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr, 0x9120000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(base);
    IMAGE_DOS_HEADER dos{}; dos.e_magic = IMAGE_DOS_SIGNATURE; dos.e_lfanew = 0x100; put(base, dos);
    IMAGE_NT_HEADERS64 nt{};
    nt.Signature = IMAGE_NT_SIGNATURE; nt.FileHeader.Machine = IMAGE_FILE_MACHINE_AMD64;
    nt.OptionalHeader.Magic = IMAGE_NT_OPTIONAL_HDR64_MAGIC; nt.OptionalHeader.SizeOfImage = 0x9120000;
    put(base + 0x100, nt);
    for (const auto& signature : sites::signatures)
    {
        const auto bytes = decode(signature.hex);
        std::memcpy(reinterpret_cast<void*>(base + signature.rva), bytes.data(), bytes.size());
    }

    // Execute the exact FIRST 62 shipping bytes, including the continuation's
    // homing, frame setup, SUB RSP,620h and the newly validated owner setup.
    // A register-preserving JMP after those bytes enters a synthetic body.
    constexpr std::uintptr_t body_rva = 0x1000;
    const std::uint8_t jump[]{0xFF, 0x25, 0, 0, 0, 0};
    std::memcpy(reinterpret_cast<void*>(base + sites::evaluation + 62), jump, sizeof(jump));
    put(base + sites::evaluation + 68, base + body_rva);
    asmjit::JitRuntime runtime;
    asmjit::CodeHolder body;
    check(body.init(runtime.environment(), base + body_rva));
    Assembler b(&body);
    b.mov(rcx, r13); // Owner setup retained the incoming owner here.
    b.mov(qword_ptr(rcx, offsetof(Snapshot, entry_rsp)), rax);
    b.mov(qword_ptr(rcx, offsetof(Snapshot, body_rsp)), rsp);
    const Gp regs[]{rax, rcx, rdx, r8, r9, r10, r11};
    for (int i = 0; i < 7; ++i) b.mov(qword_ptr(rcx, offsetof(Snapshot, gpr) + i * 8), regs[i]);
    for (int i = 0; i < 6; ++i) b.movdqu(ptr(rcx, offsetof(Snapshot, xmm) + i * 16), xmm(i));
    for (auto [offset, dest] : {std::pair{0, offsetof(Snapshot, return_address)},
         {0x28, offsetof(Snapshot, fifth)}, {0x30, offsetof(Snapshot, sixth)},
         {8, offsetof(Snapshot, home_rcx)}, {0x10, offsetof(Snapshot, home_rdx)}})
    {
        b.mov(r11, qword_ptr(rax, offset)); b.mov(qword_ptr(rcx, static_cast<int>(dest)), r11);
    }
    b.movzx(r11d, byte_ptr(rax, 0x20)); b.mov(qword_ptr(rcx, offsetof(Snapshot, home_paused)), r11);
    // Read the required fifth argument exactly as the game does, then actually
    // dereference its header. A missing/null fifth argument must fail this test.
    b.mov(r10, qword_ptr(rbp, 0x560));
    b.mov(r11, qword_ptr(r10)); b.mov(qword_ptr(rcx, offsetof(Snapshot, work_data)), r11);
    b.mov(r11d, dword_ptr(r10, 8)); b.mov(dword_ptr(rcx, offsetof(Snapshot, work_num)), r11d);
    b.mov(r11d, dword_ptr(r10, 12)); b.mov(dword_ptr(rcx, offsetof(Snapshot, work_max)), r11d);
    b.pushfq(); b.pop(qword_ptr(rcx, offsetof(Snapshot, flags)));
    b.mov(rsi, qword_ptr(rax, 0x18)); b.mov(r13, qword_ptr(rax, -0x28));
    b.add(rsp, 0x620); b.pop(rdi); b.pop(rbx); b.pop(rbp);
    b.mov(rax, 0x1122334455667788ULL); b.movdqa(xmm0, xmm5); b.stc(); b.ret();
    copy_code(body, base + body_rva);
    DWORD old{};
    assert(VirtualProtect(reinterpret_cast<void*>(base + body_rva), 0x1000, PAGE_EXECUTE_READ, &old));
    assert(VirtualProtect(reinterpret_cast<void*>(base + sites::evaluation), 0x1000, PAGE_EXECUTE_READ, &old));
    assert(FlushInstructionCache(GetCurrentProcess(), nullptr, 0));

    // One identical caller/callsite for unpatched and direct entry. Six argument
    // positions, all volatile GPR/XMM registers, return address, stack and return
    // channels are captured. The pure jump must not rely on the C++ prototype.
    alignas(16) const std::uint64_t vector[]{0x3F0000003C83126FULL, 0x8877665544332211ULL};
    asmjit::CodeHolder caller;
    check(caller.init(runtime.environment()));
    Assembler a(&caller);
    a.push(rbx); a.push(rsi); a.sub(rsp, 0x48);
    a.mov(qword_ptr(rsp, 0x20), r8); // Non-null work-list pointer supplied by test.
    a.mov(rbx, rcx); a.mov(rsi, rdx); a.mov(rcx, rsi);
    a.mov(rdx, 0x0123456789ABCDEFULL); a.mov(r8, 0x9988776655443322ULL);
    a.mov(r9, 0xFFEEDDCCBBAA0001ULL); a.mov(r10, 0x1234123412341234ULL); a.mov(r11, 0x5678567856785678ULL);
    a.mov(rax, 0xAAAABBBBCCCCDDDDULL); a.mov(qword_ptr(rsp, 0x28), rax);
    a.mov(rax, reinterpret_cast<std::uintptr_t>(vector));
    for (int i = 0; i < 6; ++i) a.movdqu(xmm(i), ptr(rax));
    a.call(rbx);
    a.mov(qword_ptr(rsi, offsetof(Snapshot, returned_rax)), rax);
    a.movdqu(ptr(rsi, offsetof(Snapshot, returned_xmm)), xmm0);
    a.pushfq(); a.pop(qword_ptr(rsi, offsetof(Snapshot, returned_flags)));
    // Entry and return diagnostics must leave the original caller's arguments
    // intact, including an extra stack canary outside the declared prototype.
    a.mov(r10, qword_ptr(rsp, 0x20)); a.mov(qword_ptr(rsi, offsetof(Snapshot, caller_fifth)), r10);
    a.mov(r10, qword_ptr(rsp, 0x28)); a.mov(qword_ptr(rsi, offsetof(Snapshot, caller_sixth)), r10);
    a.add(rsp, 0x48); a.pop(rsi); a.pop(rbx); a.ret();
    using Invoke = void (*)(std::uintptr_t, Snapshot*, WorkList*);
    Invoke invoke{};
    check(runtime.add(&invoke, &caller));
    Snapshot snapshot{};
    std::array<std::uint8_t, 4 * 32> work_data{};
    WorkList work_lists[]{{work_data.data(), 0, 4}, {work_data.data() + 32, 2, 3}};
    // Keep the actual CALL to the generated caller at one C++ callsite too.
    // /O2 could otherwise assign different outgoing stack areas to the two calls.
    Installation direct(1, EvaluationMode::Direct);
    Snapshot original{};
    provenance.reset(&snapshot, 0x200000);
    const auto original_provenance = provenance;
    Dispatch outer_dispatch{};
    Scope dispatch_scope(current_dispatch, &outer_dispatch);
    for (int pass = 0; pass < 3; ++pass)
    {
        if (pass == 1)
        {
            assert(direct.install() && direct.patches.size() == 5 && !enabled.load());
            assert(!direct.bridges.registered);
            std::uintptr_t target{};
            assert(read(direct.bridges.at(0xA00), target) && target == evaluation_trampoline);
            dump_trampoline();
            // Corrupt only the jump destination, ensuring verification catches it.
            std::int32_t disp{}; assert(read(evaluation_trampoline + 9, disp));
            const auto slot = evaluation_trampoline + 13 + disp;
            const auto correct = base + sites::evaluation + 7;
            put(slot, correct - 1); assert(!direct.detour->verify_trampoline());
            put(slot, correct); assert(direct.detour->verify_trampoline());
        }
        if (pass == 2) assert(direct.commit(false));
        snapshot = {};
        invoke(base + sites::evaluation, &snapshot, &work_lists[0]);
        if (pass == 0) original = snapshot;
        else assert(std::memcmp(&snapshot, &original, sizeof(snapshot)) == 0);
        assert(snapshot.body_rsp + 0x638 == snapshot.entry_rsp);
        assert(snapshot.gpr[0] == snapshot.entry_rsp);
        assert(snapshot.home_rcx == reinterpret_cast<std::uintptr_t>(&snapshot));
        assert(snapshot.home_rdx == 0x0123456789ABCDEFULL && snapshot.home_paused == 1);
        assert(snapshot.fifth == reinterpret_cast<std::uintptr_t>(&work_lists[0]) && snapshot.sixth == 0xAAAABBBBCCCCDDDDULL);
        assert(snapshot.work_data == reinterpret_cast<std::uintptr_t>(work_lists[0].data));
        assert(snapshot.work_num == 0 && snapshot.work_max == 4);
        assert(snapshot.caller_fifth == snapshot.fifth && snapshot.caller_sixth == snapshot.sixth);
        assert(snapshot.returned_rax == 0x1122334455667788ULL && (snapshot.returned_flags & 1));
        assert(!std::memcmp(&provenance, &original_provenance, sizeof(provenance)) && current_dispatch == &outer_dispatch);
        assert(!evaluation_seen.test() && !evaluation_returned.test()); // No C++ hook entered.
    }
    assert(direct.validate());
    std::puts("PASS: Stage 1A entry -> actual PolyHook trampoline -> shipping +7 continuation -> original return; exact register/stack/return-state comparison and untouched TLS");

    // This companion intentionally makes only the documented five-argument/void
    // guarantee. It must not claim the direct mode's six-argument transparency.
    // Retire the first unpublished detour before creating another (shared global).
    direct.detour.reset();
    Installation trace(1, EvaluationMode::Trace);
    assert(trace.install() && trace.patches.size() == 5 && !enabled.load());
    assert(!trace.bridges.registered);
    for (auto rva : sites::movement)
    {
        const std::uint8_t nops[]{0x90, 0x90};
        assert(matches(base + rva, nops, sizeof(nops)));
    }
    for (auto offset : {0xA08, 0xA10})
    {
        std::uintptr_t target{};
        assert(read(trace.bridges.at(offset), target) && target == 0);
    }
    for (const auto& signature : sites::signatures)
    {
        if (signature.rva == sites::evaluation) continue;
        auto bytes = decode(signature.hex);
        // Extended getter signatures now also cover the historical NOP bytes.
        for (const auto& patch : trace.patches)
            for (std::size_t i = 0; i < bytes.size(); ++i)
                if (signature.rva + i >= patch.rva && signature.rva + i < patch.rva + patch.size)
                    bytes[i] = patch.after[signature.rva + i - patch.rva];
        assert(matches(base + signature.rva, bytes.data(), bytes.size()));
    }
    for (int pass = 0; pass < 4; ++pass)
    {
        auto& work = work_lists[pass % 2];
        snapshot = {};
        invoke(base + sites::evaluation, &snapshot, &work);
        assert(snapshot.gpr[1] == reinterpret_cast<std::uintptr_t>(&snapshot));
        assert(snapshot.gpr[2] == 0x0123456789ABCDEFULL && (snapshot.gpr[4] & 0xFF) == 1);
        assert(!std::memcmp(snapshot.xmm[2].data(), vector, sizeof(float)));
        assert(snapshot.body_rsp + 0x638 == snapshot.entry_rsp);
        assert(snapshot.fifth == reinterpret_cast<std::uintptr_t>(&work));
        assert(snapshot.work_data == reinterpret_cast<std::uintptr_t>(work.data));
        assert(snapshot.work_num == work.num && snapshot.work_max == work.max);
        assert(snapshot.caller_fifth == snapshot.fifth && snapshot.caller_sixth == 0xAAAABBBBCCCCDDDDULL);
        assert(!std::memcmp(&provenance, &original_provenance, sizeof(provenance)) && current_dispatch == &outer_dispatch);
    }
#if MIXED_INPUT_FIX_DIAGNOSTICS
    assert(evaluation_seen.test() && evaluation_returned.test());
#else
    // Selecting a trace wrapper at runtime does not enable compiled-out markers.
    assert(!evaluation_seen.test() && !evaluation_returned.test());
#endif
    assert(trace.commit(false) && trace.validate());
    runtime.release(invoke);
    std::puts("PASS: trace companion forwards five arguments, dereferences changing non-null work-list headers, preserves caller stack arguments and provenance TLS, enters/returns repeatedly; only movement/evaluation patched");
#if MIXED_INPUT_FIX_DIAGNOSTICS
    std::puts("PASS: explicit diagnostic configuration records entry/return markers");
#else
    std::puts("PASS: normal production configuration leaves diagnostic file and entry/return markers inactive");
#endif
}
