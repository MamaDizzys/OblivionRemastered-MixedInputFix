// Diagnostic-only PE entry wrapper. /GS- on this translation unit avoids using
// a security cookie before the original CRT entry initializes it on attach.
// Forward EVERY reason and the original arguments/result to the real CRT entry.
// Do not duplicate or replace CRT/TLS initialization or destruction.
#include "ShutdownDiagnostic.hpp"
#if MIXED_INPUT_FIX_SHUTDOWN_DIAGNOSTIC
extern "C" BOOL WINAPI _DllMainCRTStartup(HINSTANCE, DWORD, LPVOID);
extern "C" BOOL WINAPI mif_shutdown_entry(HINSTANCE module, DWORD reason, LPVOID reserved)
{
    if (reason == DLL_PROCESS_DETACH)
        MIF_SHUTDOWN(dll_detach_enter, reinterpret_cast<std::uintptr_t>(reserved), 0);
    const auto result = _DllMainCRTStartup(module, reason, reserved);
    if (reason == DLL_PROCESS_DETACH)
        MIF_SHUTDOWN(dll_detach_return, reinterpret_cast<std::uintptr_t>(reserved), result);
    return result;
}
#endif
