#define MIXED_INPUT_FIX_TEST
#include "../src/dllmain.cpp"
#include "MovementBytes.hpp"
#include <cassert>
#include <cmath>
#include <limits>
using namespace mixed_input;
using namespace asmjit::x86;
namespace
{
template <typename T> void put(std::uintptr_t p, T v) { std::memcpy(reinterpret_cast<void*>(p), &v, sizeof(v)); }
struct Key
{
    std::uint64_t name{};
    void* details{};
    void* refcount{};
    std::array<std::uint8_t, 0x80> storage{};
    Key(std::uint64_t id, std::uint8_t type) : name(id)
    { details = storage.data(); put(reinterpret_cast<std::uintptr_t>(details), id); storage[0x42] = type; }
};
struct Action
{
    std::array<std::uint8_t, 0x100> action{}, instance{};
    Action() { put(reinterpret_cast<std::uintptr_t>(instance.data()), action.data()); instance[0x50] = 1; }
};
alignas(16) std::array<std::uint8_t, 0x200> mapping{};
std::array<std::uint8_t, 0x100> common{};
std::array<std::uint8_t, 0xE00> character{};
int owner{}, calls{}, direction{};
bool null_common{};
constexpr std::uintptr_t evaluation_frame = 0x200000;
constexpr std::uintptr_t handlers[]{0x488AB80, 0x488AC80, 0x488AD70, 0x488AE70};
constexpr std::uintptr_t caches[]{0xD50, 0xD4C, 0xD54, 0xD58};
void* subsystem(void*) { return null_common ? nullptr : common.data(); }
void handler(void*, void* instance)
{
    ++calls;
    reinterpret_cast<void (*)(void*, void*)>(base + handlers[direction])(
        character.data(), static_cast<std::uint8_t*>(instance) + 0x38);
}
void throwing(void*, void*) { throw std::runtime_error("movement dispatch unwind"); }
Installation* active_install{};
std::uint8_t uninstall_getter(void*)
{
    assert(active_install->commit(false));
    return common[0x91];
}
void reset() { reset_generation(&owner, evaluation_frame, evaluation_frame - 0x108); }
void dispatch_action(Action& action, int d, double value)
{
    put(reinterpret_cast<std::uintptr_t>(action.instance.data()) + 0x38, value);
    direction = d;
    Execute table[]{nullptr, &handler}; auto* binding = table;
    const auto before = calls;
    dispatch(&binding, action.instance.data(), &owner, evaluation_frame);
    assert(calls == before + 1 && !current_dispatch);
}
float cache(int d) { float f{}; assert(read(reinterpret_cast<std::uintptr_t>(character.data()) + caches[d], f)); return f; }
}
int main()
{
    open_diagnostics();
    base = reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr, 0x9120000, MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE));
    assert(base);
    IMAGE_DOS_HEADER dos{}; dos.e_magic = IMAGE_DOS_SIGNATURE; dos.e_lfanew = 0x100; put(base, dos);
    IMAGE_NT_HEADERS64 nt{}; nt.Signature = IMAGE_NT_SIGNATURE; nt.FileHeader.Machine = IMAGE_FILE_MACHINE_AMD64;
    nt.OptionalHeader.Magic = IMAGE_NT_OPTIONAL_HDR64_MAGIC; nt.OptionalHeader.SizeOfImage = 0x9120000; put(base + 0x100, nt);
    std::memcpy(reinterpret_cast<void*>(base + handlers[0]), movement_handlers, sizeof(movement_handlers));
    for (const auto& sig : sites::signatures)
    {
        auto bytes = decode(sig.hex);
        if (sig.rva >= handlers[0] && sig.rva < handlers[0] + sizeof(movement_handlers))
            assert(matches(base + sig.rva, bytes.data(), bytes.size()));
        std::memcpy(reinterpret_cast<void*>(base + sig.rva), bytes.data(), bytes.size());
    }
    for (const auto& sig : camera_composition::signatures)
    {
        const auto bytes = decode(sig.hex);
        std::memcpy(reinterpret_cast<void*>(base + sig.rva), bytes.data(), bytes.size());
    }
    // Execute complete shipping movement handlers. Their external object/subsystem
    // lookups are stubbed; getter CALLs, sign conversion, JNE, split and stores are real.
    auto stub = [&](std::uintptr_t rva, std::uintptr_t target) {
        const std::uint8_t mov[]{0x48, 0xB8}, jump[]{0xFF, 0xE0};
        std::memcpy(reinterpret_cast<void*>(base + rva), mov, 2); put(base + rva + 2, target);
        std::memcpy(reinterpret_cast<void*>(base + rva + 10), jump, 2);
    };
    for (int i = 0; i < 4; ++i) put(base + 0x870EB30 + i * 4, std::uint32_t{0x80000000});
    const std::uint64_t ids[]{101, 102, 103, 104, 105, 106};
    for (auto [rva, id] : {std::pair{sites::mouse_x, ids[0]}, {sites::mouse_y, ids[1]},
         {sites::gamepad_x, ids[2]}, {sites::gamepad_y, ids[3]}, {sites::left_x, ids[4]}, {sites::left_y, ids[5]}}) put(base + rva, id);
    for (auto rva : {sites::movement_getter_b, sites::movement_getter_f, sites::movement_getter_l,
         sites::movement_getter_r, std::uintptr_t{0x115C1E7}, std::uintptr_t{0x1134A76}, std::uintptr_t{0x9002EA}})
    {
        auto& byte = *reinterpret_cast<std::uint8_t*>(base + rva); byte ^= 1;
        Installation rejected; assert(!rejected.install() && !rejected.bridges.memory); byte ^= 1;
    }
    Installation install; assert(install.install() && install.patches.size() == 20); active_install = &install;
    // Stub external lookups only after the complete shipping preflight.
    for (auto rva : {0x1126290U, 0x357C370U, 0x394C780U}) stub(rva, reinterpret_cast<std::uintptr_t>(&subsystem));
    for (auto rva : sites::movement) { const std::uint8_t jne[]{0x75, 0x0F}; assert(matches(base + rva, jne, 2)); }
    for (auto rva : sites::movement)
        for (const auto& patch : install.patches) assert(patch.rva != rva);

    // Run the shipping magnitude/tie comparison through the installed winner
    // bridge. The only synthetic continuation returns after that single merge.
    put(base + 0x3934897, std::uint8_t{0xC3});
    asmjit::JitRuntime runtime; asmjit::CodeHolder code; check(code.init(runtime.environment())); Assembler a(&code);
    a.push(rbp); a.push(rdi); a.push(r14); a.sub(rsp, 0x20);
    a.mov(rbp, rcx); a.mov(r14, rdx); a.mov(rdi, r8);
    a.xor_(ecx, ecx); a.mov(edx, 1); a.xor_(r8d, r8d);
    a.mov(rax, 0x7FFFFFFFFFFFFFFFULL); a.movq(xmm3, rax);
    a.mov(rax, base + 0x3934858); a.call(rax);
    a.add(rsp, 0x20); a.pop(r14); a.pop(rdi); a.pop(rbp); a.ret();
    using Merge = void (*)(std::uintptr_t, void*, void*); Merge merge{}; check(runtime.add(&merge, &code));
    const auto frame = reinterpret_cast<std::uintptr_t>(mapping.data()) + 0x80;
    auto contribute = [&](Action& action, Key& key, double candidate, double accumulated = 0., bool physical = true,
                          unsigned component = 0, std::uint8_t mapped_type = 1) {
        put(frame + 0x37, evaluation_frame); put(frame + 0x3F, physical ? base + sites::mapping_return : 0);
        put(frame + 0x4F, action.action.data()); put(frame + 0x1F, &key);
        put(frame - 0x31, mapped_type); put(frame - 0x49, candidate); put(frame - 0x69, accumulated);
        if (component) record_winner(frame, &owner, action.instance.data(), component);
        else merge(frame, &owner, action.instance.data());
        double result{}; assert(read(frame - 0x69, result)); return result;
    };
    Key keyboard{0x100000007ULL, 0}, rebound{0x200000007ULL, 0};
    Key lx{ids[4], 2}, ly{ids[5], 2}, rx{ids[2], 2}, mouse{ids[0], 2}, unknown{888, 2}, button_axis{889, 1};
    Action actions[4];
    for (int global : {0, 1, 2})
    {
        common[0x91] = static_cast<std::uint8_t>(global);
        for (int d = 0; d < 4; ++d)
        {
            reset(); contribute(actions[d], d & 1 ? rebound : keyboard, 1.);
            dispatch_action(actions[d], d, .6); // Action modifier changes magnitude after winning.
            assert(cache(d) == (d & 1 ? .6f : -.6f));
            for (double v : {-1., -.36, .36, 1.})
            {
                reset(); contribute(actions[d], d < 2 ? ly : lx, v);
                dispatch_action(actions[d], d, v * .75);
                const auto expected = d & 1 ? std::fmax(v * .75, 0.) : std::fmin(v * .75, 0.);
                assert(cache(d) == static_cast<float>(expected));
            }
        }
    }
    std::puts("PASS: complete shipping handlers, all digital directions/rebinding, signed partial/full axes, action-modified magnitudes, CommonInput 0/1/2 independence");
    reset(); common[0x91] = 0;
    for (int d : {2, 3})
    {
        assert(contribute(actions[d], keyboard, 1.) == 1.);
        assert(contribute(actions[d], lx, -.84, 1.) == 1.);
        assert(provenance.lookup(provenance.generation, actions[d].action.data(), actions[d].instance.data()).source == Source::Digital);
        assert(contribute(actions[d], lx, -1., 1.) == -1.);
        dispatch_action(actions[d], d, -1.); assert(cache(d) == (d == 2 ? -1.f : 0.f));
        assert(contribute(actions[d], keyboard, 1., -1.) == 1.); // Reversed order tie.
        dispatch_action(actions[d], d, 1.); assert(cache(d) == (d == 2 ? -1.f : 1.f));
    }
    reset();
    contribute(actions[0], ly, -.7); contribute(actions[1], ly, -.7);
    contribute(actions[2], lx, -.4); contribute(actions[3], keyboard, 1.);
    contribute(actions[3], lx, -.4, 1.);
    for (int global : {0, 1})
    {
        common[0x91] = static_cast<std::uint8_t>(global);
        for (int d=0; d<4; ++d) dispatch_action(actions[d], d, d<2 ? -.5 : d==2 ? -.2 : 1.);
        assert(cache(0)==-.5f && cache(1)==0.f && cache(2)==-.2f && cache(3)==1.f);
    }
    std::puts("PASS: real magnitude arbitration, later exact-tie replacement in both horizontal actions, reversed mapping order, simultaneous independent action ownership");
    auto fallback = [&](Key& key, int d=2, bool physical=true, unsigned component=0, std::uint8_t mapped_type=1) {
        reset(); contribute(actions[d], keyboard, 1.);
        contribute(actions[d], key, 1., 1., physical, component, mapped_type);
        common[0x91]=1; dispatch_action(actions[d], d, 1.); assert(cache(d)==(d&1 ? 1.f : 0.f));
        common[0x91]=0; dispatch_action(actions[d], d, -.5); assert(cache(d)==(d&1 ? -.5f : .5f));
    };
    fallback(unknown); fallback(button_axis); fallback(ly); fallback(rx); fallback(mouse);
    fallback(keyboard,2,false); fallback(keyboard,2,true,1); fallback(keyboard,2,true,0,2);
    keyboard.details=nullptr; fallback(keyboard); keyboard.details=keyboard.storage.data();
    keyboard.storage[0]^=1; fallback(keyboard); keyboard.storage[0]^=1;
    keyboard.storage[0x42]=255; fallback(keyboard); keyboard.storage[0x42]=0;
    for (double invalid : {-1., std::numeric_limits<double>::infinity()})
    {
        reset(); contribute(actions[2], keyboard, invalid);
        assert(provenance.lookup(provenance.generation, actions[2].action.data(), actions[2].instance.data()).source == Source::Unknown);
    }
    for (int gate=0; gate<6; ++gate)
    {
        reset(); contribute(actions[2], keyboard, 1.); common[0x91]=1;
        Dispatch active{provenance.generation, actions[2].action.data(), actions[2].instance.data(), {Source::Digital, Axis::Unknown}};
        {
            Scope scope(current_dispatch, &active);
            assert(movement_x(common.data())==0 && input_x(common.data())==1);
            if(gate==0) reset(); // Same owner/frame reuse must still invalidate dispatch.
            if(gate==1) actions[2].action[0x51]=1;
            if(gate==2) actions[2].instance[0x50]=2;
            if(gate==3) enabled=false;
            if(gate==4) provenance.record(provenance.generation, actions[2].action.data(), actions[2].instance.data(), {});
            Dispatch nested{};
            if(gate==5) { Scope mask(current_dispatch,&nested); assert(movement_x(common.data())==1); }
            else assert(movement_x(common.data())==1);
        }
        enabled=true; actions[2].action[0x51]=0; actions[2].instance[0x50]=1;
        assert(movement_x(common.data())==1); // No dispatch.
    }
    reset(); contribute(actions[2], lx, -.5);
    {
        Dispatch active{provenance.generation, actions[2].action.data(), actions[2].instance.data(), {Source::LeftStick, Axis::X}};
        Scope scope(current_dispatch,&active); common[0x91]=0;
        assert(movement_x(common.data())==1 && movement_y(common.data())==0 && input_x(common.data())==0);
    }
    null_common=true; dispatch_action(actions[2],2,-.5); assert(cache(2)==.5f); null_common=false;
    Execute table[]{nullptr,&throwing}; auto* binding=table;
    try { dispatch(&binding,actions[2].instance.data(),&owner,evaluation_frame); assert(false); } catch(const std::runtime_error&) {}
    assert(!current_dispatch);
    std::puts("PASS: Unknown replacement, metadata/type/axis/caller/component gates, camera isolation, disabled/stale/nested dispatch fallback, null subsystem and unwind");
    // Uninstall from the fallback getter while the movement CALL is in flight.
    // It must return to the original cmp at +5 with the restored JNE intact.
    stub(sites::getter,reinterpret_cast<std::uintptr_t>(&uninstall_getter));
    reset(); common[0x91]=0; dispatch_action(actions[2],2,1.); assert(cache(2)==-1.f && !install.installed);
    for (const auto& sig : sites::signatures)
    {
        const auto bytes=decode(sig.hex);
        if(sig.rva==sites::getter || sig.rva==0x3934876)
            std::memcpy(reinterpret_cast<void*>(base+sig.rva),bytes.data(),bytes.size());
    }
    // Prove uninstallation restored every owned patch before repairing fixture stubs.
    for (const auto& patch : install.patches)
        assert(matches(base + patch.rva, patch.before.data(), patch.size));
    unsigned mismatches{};
    auto audit = [&](const auto& signatures) {
        for (const auto& sig : signatures)
        {
            const auto bytes = decode(sig.hex);
            if (matches(base + sig.rva, bytes.data(), bytes.size())) continue;
            ++mismatches;
            std::printf("POST-UNINSTALL RVA=0x%llX VA=0x%llX %s\nexpected:",
                static_cast<unsigned long long>(sig.rva),
                static_cast<unsigned long long>(base + sig.rva), sig.name);
            for (auto byte : bytes) std::printf(" %02X", byte);
            std::printf("\nactual:  ");
            for (std::size_t i = 0; i < bytes.size(); ++i)
                std::printf(" %02X", *reinterpret_cast<const std::uint8_t*>(base + sig.rva + i));
            std::puts("");
            // This external lookup stub belongs to this fixture, not Installation.
            assert(sig.rva == 0x1126290 && bytes.size() >= 12);
            assert(*reinterpret_cast<const std::uint16_t*>(base + sig.rva) == 0xB848);
            std::uintptr_t target{}; assert(read(base + sig.rva + 2, target));
            assert(target == reinterpret_cast<std::uintptr_t>(&subsystem));
            assert(*reinterpret_cast<const std::uint16_t*>(base + sig.rva + 10) == 0xE0FF);
            assert(matches(base + sig.rva + 12, bytes.data() + 12, bytes.size() - 12));
            std::memcpy(reinterpret_cast<void*>(base + sig.rva), bytes.data(), 12);
        }
    };
    audit(sites::signatures); audit(camera_composition::signatures);
    assert(mismatches == 1);
    assert(install.validate()); runtime.release(merge);
    std::puts("PASS: 20 patches, unchanged original movement branches, signature fail-closed, in-flight movement getter restoration at +5, full signature restoration");
}
