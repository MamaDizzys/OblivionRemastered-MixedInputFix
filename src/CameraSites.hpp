#pragma once
namespace camera_composition
{
inline constexpr sites::Signature signatures[]{
    {0x3934757, "E8 C4 31 FF FF", "camera: mapping modifier CALL"},
    {0x4641BC8, "E8 43 B6 25 00", "camera: camera X CALL"},
    {0x4640A18, "E8 E3 95 24 00", "camera: camera Y CALL"},
    {0x4641BF5, "E9 86 BF 25 00", "camera: camera X clear JMP"},
    {0x4640A45, "E9 26 9F 24 00", "camera: camera Y clear JMP"},
    {0x489D8C9, "FF 92 18 0D 00 00", "camera: stick X output CALL"},
    {0x489DB05, "FF 90 18 0D 00 00", "camera: mouse X output CALL"},
    {0x488A6B9, "FF 92 10 0D 00 00", "camera: stick Y output CALL"},
    {0x488A8F5, "FF 90 10 0D 00 00", "camera: mouse Y output CALL"},
    {0x489DB5C, "E8 0F AF FF FF", "camera: camera X common tail CALL"},
    {0x488A94C, "E8 1F E1 00 00", "camera: camera Y common tail CALL"},
    {0x3934739, "4C 8B 45 77 4C 8D 4D 97 48 8D 55 B7 F3 44 0F 11 4C 24 20 49 8B CE 0F 29 45 A7 0F 29 4D 97", "camera: mapping modifier arguments"},
    {0x392D957, "80 7A 13 01 48 8B F9 48 8B 2A 0F 29 70 E8 F3 0F 10 72 5C 0F 29 78 D8 F3 0F 10 7A 58 75 12 0F 10 42 38 0F 10 4A 48 0F 11 40 88 0F 11 48 98 EB 41", "camera: binding active value gate"},
    {0x4593DD0, "48 8B 05 F9 A8 D3 04 C3", "camera: mode manager getter"},
    {0x45964B0, "48 63 C2 0F B6 84 08 B9 00 00 00 C3", "camera: mode flag lookup"},
    {0x30C8E30, "80 B9 2A 03 00 00 00 0F 97 C0 C3", "camera: native ignore look query"},
    {0x1126290, "44 8B 49 04 45 85 C9 74 44 8B 01 85 C0 78 3E 3B 05 DF C7 FE 07 7D 36 8B C8 0F B7 C0 48 C1 E9 10 48 8D 14 40 48 8B 05 B5 C7 FE 07 48 8B 0C C8 4C 8D 04 D1 4D 85 C0 74 15 45 39 48 10 75 0F 41 8B 40 08 A9 00 00 20 30 75 04 49 8B 00 C3 33 C0 C3", "camera: object serial identity layout"},
    {0x489D353, "F3 0F 10 8E 68 0D 00 00 F3 0F 10 BE 64 0D 00 00", "camera: stick X cross-axis reads"},
    {0x488A143, "F3 0F 10 8E 64 0D 00 00 F3 0F 10 BE 68 0D 00 00", "camera: stick Y cross-axis reads"},
    {0x4898AAB, "80 BE AA 0D 00 00 00 0F 84 AC 01 00 00 48 8B 83 10 01 00 00 80 B8 A4 0C 00 00 00 0F 84 98 01 00 00 48 89 BC 24 F8 00 00 00 48 8B CE 4C 89 B4 24 00 01 00 00 0F 29 B4 24 C0 00 00 00 C6 86 AA 0D 00 00 00", "camera: common tail side-effect gate"},
};
}
