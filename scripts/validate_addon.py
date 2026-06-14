from __future__ import annotations

import ast
from pathlib import Path

from versioning import assert_versions_match


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "ZNAV_"
OPERATOR_PREFIX = "ZNAV_OT_"
PANEL_PREFIX = "ZNAV_PT_"
PROPERTY_PREFIX = "ZNAV_PG_"
PREFERENCES_PREFIX = "ZNAV_AP_"
OPERATOR_ID_PREFIX = "zbrush_navigation."


BLENDER_BASE_RULES = {
    "Operator": OPERATOR_PREFIX,
    "Panel": PANEL_PREFIX,
    "PropertyGroup": PROPERTY_PREFIX,
    "AddonPreferences": PREFERENCES_PREFIX,
    "Menu": PREFIX,
    "Header": PREFIX,
    "UIList": PREFIX,
}


def iter_python_files():
    for path in ROOT.rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path


def get_base_names(node: ast.ClassDef) -> set[str]:
    names = set()
    for base in node.bases:
        if isinstance(base, ast.Attribute):
            names.add(base.attr)
        elif isinstance(base, ast.Name):
            names.add(base.id)
    return names


def get_string_assignment(node: ast.ClassDef, name: str) -> str | None:
    for item in node.body:
        if not isinstance(item, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in item.targets):
            continue
        if isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            return item.value.value
    return None


def validate_class_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    errors = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        base_names = get_base_names(node)
        for base_name, prefix in BLENDER_BASE_RULES.items():
            if base_name in base_names and not node.name.startswith(prefix):
                errors.append(f"{path.relative_to(ROOT)}:{node.lineno} class {node.name} must start with {prefix}")
        if "Operator" in base_names:
            bl_idname = get_string_assignment(node, "bl_idname")
            if bl_idname is None or not bl_idname.startswith(OPERATOR_ID_PREFIX):
                errors.append(
                    f"{path.relative_to(ROOT)}:{node.lineno} operator {node.name} bl_idname must start with "
                    f"{OPERATOR_ID_PREFIX}"
                )
    return errors


def main() -> int:
    assert_versions_match()

    errors = []
    for path in iter_python_files():
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
        errors.extend(validate_class_names(path))

    if errors:
        for error in errors:
            print(error)
        return 1

    print("Addon validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())