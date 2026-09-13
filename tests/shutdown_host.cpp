#include <Windows.h>
#include <cassert>
#include <cstring>
int main(int argc, char** argv)
{
    assert(argc == 3);
    const auto module = LoadLibraryA(argv[1]);
    assert(module);
    const auto run = reinterpret_cast<void (*)(BOOL)>(GetProcAddress(module, "run"));
    assert(run);
    const bool pinned = std::strcmp(argv[2], "pinned") == 0;
    run(pinned);
    if (std::strcmp(argv[2], "terminate") == 0)
        TerminateProcess(GetCurrentProcess(), 0);
    assert(FreeLibrary(module));
    assert(bool(GetModuleHandleA(argv[1])) == pinned);
    return 0;
}
