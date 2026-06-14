# Sculpt User Keymap Pollution Incident

## Symptom
- Entering Sculpt Mode made the Blender Preferences > Keymap > Sculpt section appear effectively empty except for add-on-created entries.
- Normal Sculpt shortcuts disappeared or were shadowed.
- This was high risk because it affected user preferences, not only temporary add-on runtime behavior.

## Root Cause
- The implementation wrote runtime navigation overrides into `keyconfigs.user` and disabled/remapped matching RMB items there.
- During Phase 3 iteration, the approach shifted from temporary one-shot snap to custom modal behavior, but still reused the older user-keymap mutation pattern.
- A user keymap override can shadow Blender defaults. If the override is created with only a few entries, Blender's Preferences UI and effective lookup can look like the original keymap was cleared.
- The implementation optimized for shortcut precedence without preserving the contract that user keymaps are user-owned persistent state.

## Impact
- User Sculpt keymap state could be polluted by add-on runtime entries.
- Existing Sculpt shortcuts could become unavailable while the override was active or if cleanup failed.
- Debugging became confusing because the failure presented as missing Blender shortcuts rather than a direct Python exception.

## Fix
- Move add-on-owned runtime navigation entries to `bpy.context.window_manager.keyconfigs.addon`.
- Stop disabling user keymap items for normal operation.
- Add startup cleanup for legacy `zbrush_navigation.*` and earlier RMB override entries left in `keyconfigs.user`.
- Add a Blender background regression script that checks add-on keymap scope, old user keymap cleanup, runtime keymap removal, projection preservation, and object-center orbit math.

## Prevention Rules
- Treat `keyconfigs.user` as persistent user data. Do not bulk disable, clear, or rewrite user keymaps for runtime behavior.
- Add-on shortcuts should default to `keyconfigs.addon`.
- If touching `keyconfigs.user` is unavoidable, the change must be narrow, signature-tracked, reversible, and covered by a Blender background regression check proving unrelated user keymap items remain intact.
- Never create a user keymap override that contains only add-on entries unless the user explicitly requested persistent keymap customization.
- Any keymap migration/cleanup must only remove known add-on signatures, never broad event classes such as all RMB entries.

## Regression Checks
- `python scripts\validate_addon.py`
- `git diff --check`
- `python scripts\build_release_package.py`
- `& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --factory-startup --python scripts\blender_regression_check.py`