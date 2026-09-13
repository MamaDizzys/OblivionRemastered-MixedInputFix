// Exercise real PE attach/detach and the production patch transaction against
// synthetic game memory. This is not UE4SS/Unreal shutdown certification.
#define MIXED_INPUT_FIX_TEST
#include "../src/dllmain.cpp"
#include <cassert>
using namespace mixed_input;
namespace
{
struct CRTSentinel
{
    ~CRTSentinel() { MIF_SHUTDOWN(destructor_body_end, 0xC47, 0); }
} sentinel;
}
extern "C" __declspec(dllexport) void run(BOOL pinned)
{
    assert(shutdown::open());
    SetLastError(0x1234);
    MIF_SHUTDOWN(uninstall_enter, 0x1234, 0x5678);
    assert(GetLastError() == 0x1234);
    if (!pinned) return;
    base = reinterpret_cast<std::uintptr_t>(VirtualAlloc(nullptr, 0x9120000, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE));
    assert(base);
    IMAGE_DOS_HEADER dos{};
    dos.e_magic = IMAGE_DOS_SIGNATURE; dos.e_lfanew = 0x100;
    std::memcpy(reinterpret_cast<void*>(base), &dos, sizeof(dos));
    IMAGE_NT_HEADERS64 nt{};
    nt.Signature = IMAGE_NT_SIGNATURE; nt.FileHeader.Machine = IMAGE_FILE_MACHINE_AMD64;
    nt.OptionalHeader.Magic = IMAGE_NT_OPTIONAL_HDR64_MAGIC; nt.OptionalHeader.SizeOfImage = 0x9120000;
    std::memcpy(reinterpret_cast<void*>(base + 0x100), &nt, sizeof(nt));
    for (const auto& signature : sites::signatures)
    {
        const auto bytes = decode(signature.hex);
        std::memcpy(reinterpret_cast<void*>(base + signature.rva), bytes.data(), bytes.size());
    }
    for (const auto& signature : camera_composition::signatures)
    {
        const auto bytes = decode(signature.hex);
        std::memcpy(reinterpret_cast<void*>(base + signature.rva), bytes.data(), bytes.size());
    }
    installation = new Installation();
    assert(installation->install()); // Pins this fixture, as production does.
    assert(installation->patches.size() == 20 && !installation->detour);
    shutdown::journal->bridge = installation->bridges.at(0);
    enabled = false;
    MIF_SHUTDOWN(restore_begin, installation->patches.size(), 0);
    const auto restored = installation->commit(false);
    MIF_SHUTDOWN(commit_result, restored, installation->protection_warning);
    assert(restored && installation->validate());
    // Published memory and unwind registrations stay alive across CRT teardown.
    MIF_SHUTDOWN(uninstall_delete_complete, 0, 0);
}
