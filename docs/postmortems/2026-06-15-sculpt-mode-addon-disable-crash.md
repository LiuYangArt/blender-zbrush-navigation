# Sculpt Mode Add-on Disable Crash

## Symptom
- Disabling the add-on or quitting Blender while Sculpt Mode navigation override was active could crash Blender 5.1.2 with `EXCEPTION_ACCESS_VIOLATION`.
- Because the process crashed before cleanup completed, dynamic navigation shortcuts could remain in a confusing state for the next session.

## Root Cause
- `auto_load.unregister()` unregistered Blender operator classes before module-level `unregister()` hooks ran.
- Active add-on keymaps still referenced `zbrush_navigation.*` operators when those operator classes were removed.
- Blender could dereference invalid RNA/operator data during add-on disable or shutdown.
- Existing coverage only tested explicit restore before disable, not disabling while the Sculpt override was still active.

## Fix
- Run module-level `unregister()` hooks before unregistering classes, so keymap cleanup happens while operators still exist.
- Add an `exit_pre` handler that silently restores navigation before Blender shutdown.
- Use silent restore for load/exit/unregister paths to avoid status-bar timer work during teardown.
- Add a Blender regression check for `Sculpt Mode -> apply override -> addon_disable`.

## Regression Checks
- `python scripts\validate_addon.py`

- `& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python scripts\blender_regression_check.py`
- Direct crash probe: enable add-on, enter Sculpt Mode, apply override, disable add-on.