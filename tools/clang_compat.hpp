#pragma once
#include <string>
// UE4SS Helpers/String.hpp calls this template before declaring it. MSVC accepts
// that ordering; Clang requires this matching declaration. No implementation change.
namespace RC
{
    template <typename TargetCharT, typename T>
    inline auto ensure_str_as(T&& arg) -> std::basic_string<TargetCharT>;
}
