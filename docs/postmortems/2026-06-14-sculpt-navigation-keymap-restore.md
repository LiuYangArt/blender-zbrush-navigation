# Sculpt Navigation Keymap Restore Failure

## Symptom
- Leaving Sculpt Mode raised `RuntimeError: KeyMapItem ... not found in KeyMap ...` from the timer.
- RMB navigation did not take effect in Sculpt Mode.
- After using the add-on, `View3D Rotate Modal` could appear empty or lose entries such as `Cancel`.

## Root Cause
- The add-on originally stored live `KeyMapItem` Python references. During mode/keymap updates Blender can invalidate or repoint those wrappers, so removal targeted the wrong keymap item.
- Sculpt Mode has active RMB entries in the `Sculpt` keymap, including click and click-drag bindings.
- In the user's setup, runtime entries added to the `addon` keyconfig did not win against the active customized Sculpt keymap. Manually adding the same operators to the user `Sculpt` keymap worked.
- Creating a user `View3D Rotate Modal` keymap with only plugin entries shadowed Blender's default modal keymap. Removing plugin entries then left an empty user override.

## Fix
- Store keymap item signatures and keymap locations instead of live `KeyMapItem` references.
- Remove/restore by matching fresh keymap items at restore time.
- Temporarily add ZBrush navigation entries directly to the user `3D View` and `Sculpt` keymaps, then remove those exact entries on restore.
- If a user `View3D Rotate Modal` keymap is empty, repopulate the standard `Cancel` and Alt axis-snap modal entries instead of deleting the keymap.
- When adding Shift axis-snap modal entries, preserve existing modal entries and restore the Shift entries to their previous active state instead of deleting them.

## Regression Checks
- `python scripts\validate_addon.py`
- Blender factory startup user `Sculpt` keymap add/remove check.
- Blender factory startup Sculpt/Object mode switch check.
- Blender factory startup `View3D Rotate Modal` preserve-cancel check.
- Blender factory startup empty `View3D Rotate Modal` repair-fill check.