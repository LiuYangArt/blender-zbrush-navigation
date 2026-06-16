from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "blender_manifest.toml"
INIT_PATH = ROOT / "__init__.py"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
MANIFEST_ID_RE = re.compile(r"^[a-z0-9_]+$")
MANIFEST_VERSION_RE = re.compile(r'(?m)^(version[^\S\r\n]*=[^\S\r\n]*")([^"]+)("[^\S\r\n]*)(\r?)$')
BL_INFO_VERSION_RE = re.compile(
    r'(?m)^([^\S\r\n]*"version"[^\S\r\n]*:[^\S\r\n]*)'
    r'\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)([^\S\r\n]*,[^\S\r\n]*)(\r?)$'
)


BUMP_PARTS = {"major", "minor", "patch"}


def parse_version(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(version)
    if match is None:
        raise RuntimeError(f"Expected X.Y.Z version, got {version!r}")
    return tuple(int(part) for part in match.groups())


def format_version(parts: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in parts)


def read_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open("rb") as handle:
        manifest = tomllib.load(handle)
    if not isinstance(manifest, dict):
        raise RuntimeError(f"Expected TOML table in {MANIFEST_PATH}")
    return manifest


def read_manifest_id() -> str:
    package_id = read_manifest().get("id")
    if not isinstance(package_id, str) or not MANIFEST_ID_RE.fullmatch(package_id):
        raise RuntimeError(f"Missing valid id in {MANIFEST_PATH}")
    return package_id


def read_manifest_version() -> str:
    version = read_manifest().get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError(f"Missing string version in {MANIFEST_PATH}")
    parse_version(version)
    return version


def read_release_metadata() -> tuple[str, str]:
    return read_manifest_id(), read_manifest_version()


def read_bl_info_version() -> str:
    tree = ast.parse(INIT_PATH.read_text(encoding="utf-8"), filename=str(INIT_PATH))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "bl_info" for target in node.targets):
            continue
        bl_info = ast.literal_eval(node.value)
        version = bl_info.get("version")
        if not isinstance(version, tuple) or len(version) != 3 or not all(isinstance(part, int) for part in version):
            raise RuntimeError(f"Missing integer tuple bl_info version in {INIT_PATH}")
        return format_version(version)
    raise RuntimeError(f"Missing bl_info in {INIT_PATH}")


def replace_once(path: Path, pattern: re.Pattern[str], replacement: str) -> None:
    with path.open("r", encoding="utf-8", newline="") as handle:
        text = handle.read()
    text, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Expected exactly one version field in {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def write_manifest_version(version: str) -> None:
    parse_version(version)
    replace_once(MANIFEST_PATH, MANIFEST_VERSION_RE, rf'\g<1>{version}\g<3>\g<4>')


def sync_bl_info_version(version: str | None = None) -> str:
    version = version or read_manifest_version()
    major, minor, patch = parse_version(version)
    replace_once(INIT_PATH, BL_INFO_VERSION_RE, rf'\g<1>({major}, {minor}, {patch})\g<5>\g<6>')
    return version


def bump_version(part: str = "patch") -> str:
    if part not in BUMP_PARTS:
        raise RuntimeError(f"Expected bump part to be one of {sorted(BUMP_PARTS)}, got {part!r}")

    major, minor, patch = parse_version(read_manifest_version())
    if part == "major":
        version_parts = (major + 1, 0, 0)
    elif part == "minor":
        version_parts = (major, minor + 1, 0)
    else:
        version_parts = (major, minor, patch + 1)

    version = format_version(version_parts)
    write_manifest_version(version)
    sync_bl_info_version(version)
    return version


def bump_patch() -> str:
    return bump_version("patch")


def assert_versions_match(release_tag: str | None = None) -> str:
    version = read_manifest_version()
    bl_info_version = read_bl_info_version()
    if bl_info_version != version:
        raise RuntimeError(
            "Version mismatch: "
            f"{MANIFEST_PATH.name} has {version}, {INIT_PATH.name} bl_info has {bl_info_version}. "
            "Run: python scripts/versioning.py sync"
        )
    if release_tag is not None and release_tag != f"v{version}":
        raise RuntimeError(f"Release tag mismatch: expected v{version}, got {release_tag}")
    return version


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage ZBrush Navigation versions.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("current")
    subparsers.add_parser("metadata")
    subparsers.add_parser("sync")
    set_parser = subparsers.add_parser("set")
    set_parser.add_argument("version")
    bump_parser = subparsers.add_parser("bump")
    bump_parser.add_argument("part", choices=sorted(BUMP_PARTS), nargs="?", default="patch")
    subparsers.add_parser("bump-patch")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--release-tag")
    args = parser.parse_args()

    if args.command == "current":
        print(read_manifest_version())
    elif args.command == "metadata":
        package_id, version = read_release_metadata()
        print(f"{package_id} {version}")
    elif args.command == "sync":
        print(sync_bl_info_version())
    elif args.command == "set":
        write_manifest_version(args.version)
        print(sync_bl_info_version(args.version))
    elif args.command == "bump":
        print(bump_version(args.part))
    elif args.command == "bump-patch":
        print(bump_patch())
    elif args.command == "check":
        print(assert_versions_match(args.release_tag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())