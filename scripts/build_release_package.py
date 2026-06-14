from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

from versioning import assert_versions_match


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ID = "zbrush_navigation"

ROOT_FILES = (
    "__init__.py",
    "auto_load.py",
    "blender_manifest.toml",
)
PACKAGE_DIRS = (
    "functions",
    "operators",
    "panels",
    "properties",
)
EXCLUDED_PARTS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
EXCLUDED_BLEND_BACKUPS = (".blend1", ".blend2", ".blend@", ".blend~")


def should_include(path: Path) -> bool:
    if EXCLUDED_PARTS.intersection(path.parts):
        return False
    if path.suffix in EXCLUDED_SUFFIXES:
        return False
    if path.name.endswith(EXCLUDED_BLEND_BACKUPS):
        return False
    return path.is_file()


def iter_package_files() -> list[Path]:
    files: list[Path] = []

    for relative in ROOT_FILES:
        path = ROOT / relative
        if not path.is_file():
            raise FileNotFoundError(f"Required package file not found: {path}")
        files.append(path)

    for relative in PACKAGE_DIRS:
        directory = ROOT / relative
        if not directory.is_dir():
            raise FileNotFoundError(f"Required package directory not found: {directory}")
        files.extend(path for path in directory.rglob("*") if should_include(path))

    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def build_package(output_dir: Path, release_tag: str | None = None) -> Path:
    version = assert_versions_match(release_tag)
    files = iter_package_files()
    if not files:
        raise RuntimeError("No package files found")

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f"{PACKAGE_ID}-v{version}.zip"
    if archive_path.exists():
        archive_path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())

    return archive_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the ZBrush Navigation release zip.")
    parser.add_argument("--output", type=Path, default=ROOT / "dist", help="Output directory for the zip file.")
    parser.add_argument("--release-tag", help="Expected GitHub release tag. Must be v{plugin version}.")
    args = parser.parse_args()

    archive_path = build_package(args.output.resolve(), args.release_tag)
    print(archive_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())