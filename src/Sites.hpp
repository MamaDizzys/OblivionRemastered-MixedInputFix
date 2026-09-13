#pragma once
#include <cstdint>

namespace mixed_input::sites
{
inline constexpr std::uintptr_t evaluation = 0x392B630;
inline constexpr std::uintptr_t reset_call = 0x392B6A6;
inline constexpr std::uintptr_t reset_original = 0x3939FA0;
inline constexpr std::uintptr_t winner = 0x3934891;
// Include the vtable load immediately preceding dispatch CALL at RVA 0x392CD18.
inline constexpr std::uintptr_t dispatch = 0x392CD15;
inline constexpr std::uintptr_t mapping_return = 0x392BCBF;
inline constexpr std::uintptr_t getter = 0x2E6CC30;
inline constexpr std::uintptr_t camera_x = 0x489D210;
inline constexpr std::uintptr_t camera_y = 0x488A000;
inline constexpr std::uintptr_t getter_x = 0x489D2F9;
inline constexpr std::uintptr_t getter_y = 0x488A0E9;
inline constexpr std::uintptr_t mouse_x = 0x91132C0;
inline constexpr std::uintptr_t mouse_y = 0x91132D8;
inline constexpr std::uintptr_t gamepad_x = 0x9113F20;
inline constexpr std::uintptr_t gamepad_y = 0x9113F38;
inline constexpr std::uintptr_t left_x = 0x9113ED8;
inline constexpr std::uintptr_t left_y = 0x9113EF0;
inline constexpr std::uintptr_t movement_getter_b = 0x488AC3C;
inline constexpr std::uintptr_t movement_getter_f = 0x488AD32;
inline constexpr std::uintptr_t movement_getter_l = 0x488AE2C;
inline constexpr std::uintptr_t movement_getter_r = 0x488AF22;

struct Signature { std::uintptr_t rva; const char* hex; const char* name; };
// Exact on-disk bytes, with no wildcards. Also checked against the loaded image.
inline constexpr Signature signatures[] = {
    {movement_getter_b, "E8 EF 1F 5E FE 3C 01 75 0F 0F 57 C0", "backward getter CALL and branch"},
    {movement_getter_f, "E8 F9 1E 5E FE 3C 01 75 0F 0F 57 C0", "forward getter CALL and branch"},
    {movement_getter_l, "E8 FF 1D 5E FE 3C 01 75 0F 0F 57 C0", "left getter CALL and branch"},
    {movement_getter_r, "E8 09 1D 5E FE 3C 01 75 0F 0F 57 C0", "right getter CALL and branch"},
    {0x392BAE5, "49 8B CE E8 E3 06 83 FD", "physical key metadata resolution"},
    {0x115C1D0, "40 53 48 83 EC 20 48 8B D9 E8 F2 88 FD FF 48 8B 43 08 48 85 C0 74 11 0F B6 40 42 2C 02 3C 02 0F 96 C0 48 83 C4 20 5B C3", "FKey analog query and cached details"},
    {0x1133E4F, "48 8B 02 41 8B F1 48 89 01", "FKeyDetails embedded identity"},
    {0x1134A64, "0F BA E2 0A 73 07 41 C6 40 42 01 EB 23 F6 C2 20 74 07 41 C6 40 42 02 EB 17 0F BA E2 0B 73 07 41 C6 40 42 03 EB 0A C0 EA 04 80 E2 04 41 88 50 42", "FKeyDetails key type encoding"},
    {0x9002EA, "48 8D 15 87 95 59 06 48 8D 0D E0 3B 81 08 E8 43 B4 63 00", "LeftX runtime identity initializer"},
    {0x90032A, "48 8D 15 57 95 59 06 48 8D 0D B8 3B 81 08 E8 03 B4 63 00", "LeftY runtime identity initializer"},
    {0x39346F0, "0F B6 77 50 0F 57 F6 48 8B 45 67 8B DE 40 88 75 CF 8B CE F2", "mapping value type local"},
    {0x3934831, "3B DA 0F 11 7D B7 0F 42 C2 F2 44 0F 11 45 C7 F2 0F 11 4D A7", "mapped candidate stack copy"},
    {evaluation, "48 8B C4 44 88 48 20 48 89 50 10 48 89 48 08 55 53 57 48 8D A8 C8 FA FF FF 48 81 EC 20 06 00 00", "evaluation entry"},
    {0x392B650, "48 89 70 18 41 0F B6 F1 4C 89 60 E0 4C 89 68 D8 4C 8B E9 4C 89 70 D0 48 81 C1 F8 05 00 00", "evaluation owner setup"},
    {0x392B69E, "44 0F 28 F2 48 89 4D 90 E8 F5 E8 00 00", "evaluation reset"},
    {0x392BCBA, "E8 91 88 00 00 EB 0E", "physical mapping caller"},
    {0x3934550, "48 8B C4 48 89 50 10 55 57 41 54 48 8D 68 C1 48 81 EC F0 00 00 00 48 89 58 08 48 8B DA 4C 89 70 E0 4C 8B F1 4C 89 78 D8 44 0F 29 48 98 44 0F 28 CA E8 AA 9D FF FF 48 8B F8", "mapping frame and instance"},
    {0x39347CC, "48 8B 07 41 39 4F 08 44 88 54 24 30 41 0F 9F C4 44 0F B6 40 51", "action policy field"},
    {0x3934858, "45 85 C0 74 19 44 3B C2 75 14 F2 0F 10 44 CD B7 F2 0F 58 44 CD 97 F2 0F 11 44 CD 97 EB 21", "additive bypass"},
    {0x3934876, "F2 0F 10 54 CD B7 F2 0F 10 44 CD 97 0F 28 CA 0F 54 CB 0F 54 C3 66 0F 2F C8 72 06 F2 0F 11 54 CD 97 48 FF C1 49 3B C9 7C B9", "winner and tie branch"},
    {0x392CD0F, "49 8B 0E 48 8B D7 48 8B 01 FF 50 08 49 8D BD A8 05 00 00", "dispatch contract"},
    {getter, "0F B6 81 91 00 00 00 C3", "original CommonInput getter"},
    {getter_x, "E8 32 F9 5C FE 3C 01 0F 85 02 06 00 00", "horizontal getter and branch"},
    {getter_y, "E8 42 2B 5E FE 3C 01 0F 85 02 06 00 00", "vertical getter and branch"},
    {0x488AC41, "3C 01 75 0F 0F 57 C0", "backward movement"},
    {0x488AD37, "3C 01 75 0F 0F 57 C0", "forward movement"},
    {0x488AE31, "3C 01 75 0F 0F 57 C0", "left movement"},
    {0x488AF27, "3C 01 75 0F 0F 57 C0", "right movement"},
};
inline constexpr std::uintptr_t movement[] = {0x488AC43, 0x488AD39, 0x488AE33, 0x488AF29};
}
