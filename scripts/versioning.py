from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "blender_manifest.toml"
INIT_PATH = ROOT / "__init__.py"
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
MANIFEST_VERSION_RE = re.compile(r'(?m)^(version[^\S\r\n]*=[^\S\r\n]*")([^"]+)("[^\S\r\n]*)(\r?)$')
BL_INFO_VERSION_RE = re.compile(
    r'(?m)^([^\S\r\n]*"version"[^\S\r\n]*:[^\S\r\n]*)'
    r'\((\d+)\s*,\s*(\d+)\s*,\s*(\d+)\)([^\S\r\n]*,[^\S\r\n]*)(\r?)$'
)


def parse_version(version: str) -> tuple[int, int, int]:
    match = VERSION_RE.fullmatch(version)
    if match is None:
        raise RuntimeError(f"Expected X.Y.Z version, got {version!r}")
    return tuple(int(part) for part in match.groups())


def format_version(parts: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in parts)


def read_manifest_version() -> str:
    with MANIFEST_PATH.open("rb") as handle:
        manifest = tomllib.load(handle)
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError(f"Missing string version in {MANIFEST_PATH}")
    parse_version(version)
    return version


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


def bump_patch() -> str:
    major, minor, patch = parse_version(read_manifest_version())
    version = format_version((major, minor, patch + 1))
    write_manifest_version(version)
    sync_bl_info_version(version)
    return version


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
    subparsers.add_parser("sync")
    set_parser = subparsers.add_parser("set")
    set_parser.add_argument("version")
    subparsers.add_parser("bump-patch")
    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--release-tag")
    args = parser.parse_args()

    if args.command == "current":
        print(read_manifest_version())
    elif args.command == "sync":
        print(sync_bl_info_version())
    elif args.command == "set":
        write_manifest_version(args.version)
        print(sync_bl_info_version(args.version))
    elif args.command == "bump-patch":
        print(bump_patch())
    elif args.command == "check":
        print(assert_versions_match(args.release_tag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())