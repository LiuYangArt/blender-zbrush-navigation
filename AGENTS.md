# AGENTS.md

## Project
- Blender add-on: `zbrush_navigation`
- Target Blender API: 5.0+
- This project uses `auto_load.py`; do not manually maintain class/module registration lists.

## Structure
- `__init__.py`: add-on entrypoint, delegates registration to `auto_load`
- `auto_load.py`: discovers submodules and registers Blender classes in dependency order
- `operators/`: `bpy.types.Operator` classes
- `panels/`: `bpy.types.Panel` classes
- `properties/`: `bpy.types.PropertyGroup` classes and pointer/collection property attach/detach hooks
- `functions/`: pure helpers and Blender utility functions; no class registration required
- `scripts/`: validation and development scripts
- `docs/postmortems/`: required when debugging takes more than one iteration

## Blender Naming Rules
- Operator class names: `ZNAV_OT_*`
- Operator `bl_idname`: `zbrush_navigation.*`
- Panel class names: `ZNAV_PT_*`
- Panel `bl_idname`: `ZNAV_PT_*`
- PropertyGroup class names: `ZNAV_PG_*`
- AddonPreferences class names: `ZNAV_AP_*`
- Menu/Header/UIList classes must also use `ZNAV_*` prefixes.
- Python modules, functions, variables, and properties use `snake_case`.
- Do not use broad silent fallback; add context and re-raise errors unless explicitly building product-level recovery.

## Blender Operator 交互规范
- 新增或修改 Blender operator 的参数交互时，默认先参考项目内已有同类工具，优先复用现有模式。
- 对可重复执行、参数可后调的工具，默认采用 bevel operator 的交互方式：
  `bl_options = {"REGISTER", "UNDO"}`，提供 `draw()`，`invoke()` 中完成必要校验后直接 `return self.execute(context)`。
- 这类参数不应在 operator 执行前弹出阻塞式窗口；应让参数出现在 Blender 左下角的 `Adjust Last Operation` 面板中。
- 除非用户明确要求，或该工具在执行前必须先确认/输入参数，否则不要使用 `invoke_props_dialog`、`invoke_props_popup`、`invoke_confirm` 这类阻塞式交互。
- 如果项目内已有对应的 scene/global 参数同步模式，新增参数时应优先沿用，不要单独发明另一套交互或存储方式。

## Registration
- Do not manually register imported modules in `__init__.py`.
- Add new Blender classes anywhere under this package; `auto_load` discovers them.
- Module-level `register()` / `unregister()` are allowed only for non-class hooks such as attaching `PointerProperty` to `WindowManager` or `Scene`.
- Keep `unregister()` symmetrical with `register()`.

## Release Packaging
- Local package: `python scripts/build_release_package.py`
- Version source of truth: `blender_manifest.toml`; use `python scripts/versioning.py sync` to update `__init__.py` `bl_info` from it.
- Package script only includes: `__init__.py`, `auto_load.py`, `blender_manifest.toml`, `functions/`, `operators/`, `panels/`, `properties/`.

## Verification
- Syntax and naming check: `python scripts/validate_addon.py`
- Package check: `python scripts/build_release_package.py`
- Blender check: run Blender 5.0+ with this add-on enabled and inspect the View3D Sidebar `ZBrush Nav` tab.