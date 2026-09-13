#!/usr/bin/env python3

import argparse
import hashlib
import shutil
import zipfile
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


parser = argparse.ArgumentParser(
    description="Package a clean Mixed Input Logic Fix (MILF) UE4SS release archive."
)
parser.add_argument(
    "dll",
    type=Path,
    help="Explicit production DLL to package",
)
parser.add_argument(
    "--version",
    required=True,
    help="Release version, e.g. 1.0.0",
)
args = parser.parse_args()

repo = Path(__file__).resolve().parents[1]
source = args.dll.expanduser().resolve()

if not source.is_file():
    parser.error(f"DLL does not exist: {source}")

if source.suffix.lower() != ".dll":
    parser.error(f"Expected a .dll file: {source}")

blocked = (
    "prototype",
    "diagnostic",
    "shutdown",
    "trace",
    "-tests",
    "_tests",
)
lower_name = source.name.lower()
if any(word in lower_name for word in blocked):
    parser.error(f"Refusing to package experimental/test DLL: {source.name}")

with source.open("rb") as f:
    if f.read(2) != b"MZ":
        parser.error(f"File does not look like a Windows PE DLL: {source}")

release = repo / "release"
staging = release / ".staging"
mod = staging / "ue4ss" / "mods" / "MixedInputFix"
dll_dir = mod / "dlls"

if staging.exists():
    shutil.rmtree(staging)

dll_dir.mkdir(parents=True)
(mod / "enabled.txt").write_bytes(b"")

notices = repo / "THIRD_PARTY_NOTICES.txt"
if not notices.is_file():
    raise RuntimeError(f"Missing third-party notices: {notices}")

shutil.copy2(notices, mod / "THIRD_PARTY_NOTICES.txt")
shutil.copy2(source, dll_dir / "main.dll")

archive = release / f"MixedInputLogicFix-{args.version}.zip"
if archive.exists():
    archive.unlink()

with zipfile.ZipFile(
    archive,
    "w",
    compression=zipfile.ZIP_DEFLATED,
    compresslevel=9,
) as zf:
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            zf.write(path, path.relative_to(staging))

contents = [
    path.relative_to(staging).as_posix()
    for path in sorted(staging.rglob("*"))
    if path.is_file()
]

expected = [
    "ue4ss/mods/MixedInputFix/THIRD_PARTY_NOTICES.txt",
    "ue4ss/mods/MixedInputFix/dlls/main.dll",
    "ue4ss/mods/MixedInputFix/enabled.txt",
]

if sorted(contents) != sorted(expected):
    raise RuntimeError(f"Unexpected package contents: {contents}")

print(f"Archive: {archive}")
print(f"DLL SHA256:     {sha256(source)}")
print(f"Archive SHA256: {sha256(archive)}")
print("Contents:")
for entry in contents:
    print(f"  {entry}")
