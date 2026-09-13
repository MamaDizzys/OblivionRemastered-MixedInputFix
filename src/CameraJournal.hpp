#pragma once
// Prototype-only evidence writer; included inside camera_composition.
struct Record
{
    std::uint64_t sequence{}, generation{}, frame{}, owner{}, action{}, instance{}, receiver{}, call{}, target{};
    double mouse{}, stick{}, input{}, angular{}, before{}, after{};
    std::uint32_t event{}, axis{}, source{}, reason{}, thread{}, flags{};
    InventoryDiagnostic inventory{};
};
static_assert(sizeof(Record) == 304);
struct Journal
{
    char magic[8]{};
    std::uint32_t version{}, stride{}, capacity{}, pid{};
    std::atomic<std::uint64_t> next{};
    std::uint64_t game{};
    std::uint8_t padding[24]{};
    Record records[4096]{};
};
static_assert(offsetof(Journal, records) == 64);
Journal* journal{}; // Mapped once before publication, retained with pinned code.
std::atomic<std::uint32_t> rejection_seen{};
std::atomic<std::uint32_t> inventory_seen[2]{}; // First predicate per axis; at most 52 records.
std::atomic<std::uint64_t> calls{}, singles{};

bool open_journal() noexcept
{
    HMODULE self{}; wchar_t path[32768]{};
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
        reinterpret_cast<LPCWSTR>(&open_journal), &self)) return false;
    const auto n = GetModuleFileNameW(self, path, static_cast<DWORD>(std::size(path)));
    if (!n || n + 60 >= std::size(path)) return false;
    // Unique evidence per process; never overwrite a previous launch.
    swprintf_s(path + n, std::size(path) - n, L".camera-%lu.bin", GetCurrentProcessId());
    auto file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
        nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    auto mapping = CreateFileMappingW(file, nullptr, PAGE_READWRITE, 0, sizeof(Journal), nullptr);
    if (!mapping) { CloseHandle(file); return false; }
    auto* memory = MapViewOfFile(mapping, FILE_MAP_WRITE | FILE_MAP_READ, 0, 0, sizeof(Journal));
    CloseHandle(mapping); CloseHandle(file);
    if (!memory) return false;
    journal = new (memory) Journal{};
    std::memcpy(journal->magic, "MIFCAM01", 8);
    journal->version=2; journal->stride=sizeof(Record); journal->capacity=4096;
    journal->pid=GetCurrentProcessId(); journal->game=base;
    return true;
}
void record(Record r) noexcept
{
    if (!journal) return;
    const auto i = journal->next.fetch_add(1, std::memory_order_relaxed);
    if (i >= std::size(journal->records)) return; // Bounded, preserves first proof.
    r.thread = GetCurrentThreadId();
    auto& dst = journal->records[i];
    std::memcpy(reinterpret_cast<char*>(&dst)+8, reinterpret_cast<char*>(&r)+8, sizeof(r)-8);
    // A reader accepts only committed slots. No file I/O, formatter or game logger.
    InterlockedExchange64(reinterpret_cast<volatile LONG64*>(&dst.sequence), i+1);
}
