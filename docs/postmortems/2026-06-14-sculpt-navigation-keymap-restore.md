# Sculpt Navigation Keymap Restore Failure

## Symptom
- Leaving Sculpt Mode raised `RuntimeError: KeyMapItem ... not found in KeyMap ...` from the timer.
- RMB navigation did not take effect in Sculpt Mode.

## Root Cause
- The add-on stored live `KeyMapItem` Python references. During mode/keymap updates Blender can invalidate or repoint those wrappers, so removal targeted the wrong keymap item.
- Sculpt Mode has active RMB entries in the `Sculpt` keymap, including click and click-drag bindings.
- In the user's setup, runtime entries added to the `addon` keyconfig did not win against the active customized Sculpt keymap. Manually adding the same operators to the user `Sculpt` keymap worked.

## Fix
- Store keymap item signatures and keymap locations instead of live `KeyMapItem` references.
- Remove/restore by matching fresh keymap items at restore time.
- Temporarily add ZBrush navigation entries directly to the user `3D View` and `Sculpt` keymaps, then remove those exact entries on restore.
- Temporarily disable RMB conflicts in `3D View`, `Sculpt`, and Sculpt tool keymaps while Sculpt Mode override is active.

## Regression Checks
- `python scripts\validate_addon.py`
- Blender factory startup user `Sculpt` keymap add/remove check.
- Blender factory startup Sculpt/Object mode switch check.
- Blender user-preferences conflict check against existing Sculpt RMB bindings.