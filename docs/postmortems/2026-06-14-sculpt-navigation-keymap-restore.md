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

## Follow-up: Rotate Modal Duplicate Snap Keys

### Symptom
- In Sculpt Mode, `View3D Rotate Modal` showed extra Axis Snap / Axis Snap Off rows for Shift while the original Alt rows remained active.
- A follow-up in-place mutation fix could freeze Blender when entering Sculpt Mode.

### Root Cause
- The Sculpt override added Shift modal entries instead of retargeting the existing Axis Snap modal entries.
- The repair path could also add default modal entries before snapshotting, which violated the intended restore-only contract.
- Some Blender sessions expose an empty user `View3D Rotate Modal`; raising from the mode timer repeats the failure during mode entry.
- Mutating live modal key item event fields is riskier than replacing the keymap contents from serialized data.

### Fix
- Snapshot the rotate modal keymap before changes.
- Only touch an existing user rotate modal keymap when it already has Axis Snap rows.
- Rebuild the same number of modal rows from serialized data, retargeting Axis Snap to Left/Right Shift and forcing those rows active.
- Restore the exact snapshot on exit.

### Regression Checks
- `python scripts\validate_addon.py`
- Blender 5.1.2 background empty rotate modal apply/restore script.
- Blender 5.1.2 background existing rotate modal apply/restore script.
- Blender 5.1.2 background Sculpt/Object mode transition script.
