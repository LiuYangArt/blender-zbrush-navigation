from __future__ import annotations

from dataclasses import dataclass, field

import bpy
from bpy.app.handlers import persistent


TIMER_INTERVAL_SECONDS = 0.25
VIEW3D_KEYMAP_NAME = "3D View"
SCULPT_KEYMAP_NAME = "Sculpt"
VIEW3D_ROTATE_MODAL_KEYMAP_NAME = "View3D Rotate Modal"
NAVIGATION_KEYMAP_NAMES = (VIEW3D_KEYMAP_NAME, SCULPT_KEYMAP_NAME)
RIGHT_MOUSE_TARGET_MODIFIERS = {
    (False, False, False, False),  # RMB
    (False, True, False, False),  # Ctrl RMB
    (False, False, True, False),  # Alt RMB
    (True, False, False, False),  # Shift RMB
}
AXIS_SNAP_MODAL_VALUES = {"AXIS_SNAP_ENABLE", "AXIS_SNAP_DISABLE"}
STATUS_MESSAGE_DURATION_SECONDS = 2.5


@dataclass(frozen=True)
class _KeymapLocation:
    keyconfig_name: str
    keymap_name: str


@dataclass(frozen=True)
class _KeymapItemSignature:
    idname: str
    propvalue: str
    type: str
    value: str
    any: bool
    shift: bool
    ctrl: bool
    alt: bool
    oskey: bool
    key_modifier: str
    direction: str
    map_type: str


@dataclass(frozen=True)
class _ActiveStateSnapshot:
    location: _KeymapLocation
    signature: _KeymapItemSignature


@dataclass(frozen=True)
class _AddedKeymapItem:
    location: _KeymapLocation
    signature: _KeymapItemSignature


@dataclass
class _RuntimeState:
    applied: bool = False
    original_emulate_3_button: bool | None = None
    active_snapshots: list[_ActiveStateSnapshot] = field(default_factory=list)
    added_keymap_items: list[_AddedKeymapItem] = field(default_factory=list)


_runtime_state = _RuntimeState()
_timer_enabled = False
_status_message_token = 0


def format_settings_summary(settings) -> str:
    enabled = "enabled" if settings.enable_zbrush_navigation else "disabled"
    active = "active" if _runtime_state.applied else "inactive"
    return f"ZBrush Navigation is {enabled}; Sculpt override is {active}"


def is_sculpt_mode_active() -> bool:
    return getattr(bpy.context, "mode", None) == "SCULPT"


def synchronize_navigation_state() -> None:
    settings = getattr(bpy.context.window_manager, "zbrush_navigation_settings", None)
    should_apply = bool(settings and settings.enable_zbrush_navigation and is_sculpt_mode_active())
    if should_apply and not _runtime_state.applied:
        apply_zbrush_navigation()
    elif not should_apply and _runtime_state.applied:
        restore_zbrush_navigation()


def apply_zbrush_navigation() -> None:
    if _runtime_state.applied:
        return

    preferences = bpy.context.preferences
    _runtime_state.original_emulate_3_button = preferences.inputs.use_mouse_emulate_3_button

    try:
        _disable_conflicting_keymap_items()
        _add_zbrush_keymap_items()
        preferences.inputs.use_mouse_emulate_3_button = False
        _runtime_state.applied = True
        _show_status_message("ZBrush Navigation: Sculpt Mode override enabled")
    except Exception as error:
        restore_zbrush_navigation()
        raise RuntimeError("Failed to apply ZBrush Navigation sculpt keymaps") from error


def restore_zbrush_navigation() -> None:
    preferences = bpy.context.preferences
    _remove_added_keymap_items()
    _restore_disabled_keymap_items()
    if _runtime_state.original_emulate_3_button is not None:
        preferences.inputs.use_mouse_emulate_3_button = _runtime_state.original_emulate_3_button
    _show_status_message("ZBrush Navigation: original navigation restored")
    _reset_runtime_state()


def _reset_runtime_state() -> None:
    _runtime_state.applied = False
    _runtime_state.original_emulate_3_button = None
    _runtime_state.active_snapshots.clear()
    _runtime_state.added_keymap_items.clear()


def _show_status_message(message: str) -> None:
    global _status_message_token
    _status_message_token += 1
    token = _status_message_token
    bpy.context.workspace.status_text_set(message)
    print(message)

    def clear_status_message() -> None:
        if token == _status_message_token:
            bpy.context.workspace.status_text_set(None)
        return None

    bpy.app.timers.register(clear_status_message, first_interval=STATUS_MESSAGE_DURATION_SECONDS)


def _disable_conflicting_keymap_items() -> None:
    for keyconfig_name in ("user", "default"):
        keyconfig = getattr(bpy.context.window_manager.keyconfigs, keyconfig_name, None)
        if keyconfig is None:
            continue

        for keymap in _iter_navigation_conflict_keymaps(keyconfig):
            for keymap_item in keymap.keymap_items:
                if _is_conflicting_right_mouse_item(keymap_item):
                    _disable_keymap_item(keyconfig_name, keymap, keymap_item)

        rotate_modal_keymap = _get_existing_keymap(keyconfig, VIEW3D_ROTATE_MODAL_KEYMAP_NAME)
        if rotate_modal_keymap is not None:
            for keymap_item in rotate_modal_keymap.keymap_items:
                if _is_axis_snap_modal_item(keymap_item):
                    _disable_keymap_item(keyconfig_name, rotate_modal_keymap, keymap_item)


def _iter_navigation_conflict_keymaps(keyconfig: bpy.types.KeyConfig):
    for keymap in keyconfig.keymaps:
        if keymap.name in NAVIGATION_KEYMAP_NAMES or keymap.name.startswith("3D View Tool: Sculpt"):
            yield keymap


def _disable_keymap_item(keyconfig_name: str, keymap: bpy.types.KeyMap, keymap_item: bpy.types.KeyMapItem) -> None:
    if not keymap_item.active:
        return
    _runtime_state.active_snapshots.append(
        _ActiveStateSnapshot(
            location=_KeymapLocation(keyconfig_name, keymap.name),
            signature=_get_keymap_item_signature(keymap_item),
        )
    )
    keymap_item.active = False


def _restore_disabled_keymap_items() -> None:
    for snapshot in reversed(_runtime_state.active_snapshots):
        keymap = _get_runtime_keymap(snapshot.location)
        if keymap is None:
            print(f"ZBrush Navigation: skipped restore; keymap not found: {snapshot.location}")
            continue
        restored = _set_first_matching_keymap_item_active(keymap, snapshot.signature, active=True)
        if not restored:
            print(f"ZBrush Navigation: skipped restore; keymap item not found: {snapshot.location}")


def _add_zbrush_keymap_items() -> None:
    user_keyconfig = bpy.context.window_manager.keyconfigs.user
    if user_keyconfig is None:
        raise RuntimeError("Blender user keyconfig is not available")

    for keymap_name in NAVIGATION_KEYMAP_NAMES:
        keymap = _get_or_create_keymap(user_keyconfig, keymap_name, space_type=_space_type_for_keymap(keymap_name))
        _add_keymap_item("user", keymap, "view3d.rotate", "RIGHTMOUSE", "PRESS")
        _add_keymap_item("user", keymap, "view3d.zoom", "RIGHTMOUSE", "PRESS", ctrl=True)
        _add_keymap_item("user", keymap, "view3d.move", "RIGHTMOUSE", "PRESS", alt=True)

    rotate_modal_keymap = _get_or_create_keymap(user_keyconfig, VIEW3D_ROTATE_MODAL_KEYMAP_NAME, modal=True)
    _add_modal_keymap_item("user", rotate_modal_keymap, "AXIS_SNAP_ENABLE", "LEFT_SHIFT", "PRESS")
    _add_modal_keymap_item("user", rotate_modal_keymap, "AXIS_SNAP_DISABLE", "LEFT_SHIFT", "RELEASE")
    _add_modal_keymap_item("user", rotate_modal_keymap, "AXIS_SNAP_ENABLE", "RIGHT_SHIFT", "PRESS")
    _add_modal_keymap_item("user", rotate_modal_keymap, "AXIS_SNAP_DISABLE", "RIGHT_SHIFT", "RELEASE")


def _add_keymap_item(
    keyconfig_name: str,
    keymap: bpy.types.KeyMap,
    idname: str,
    event_type: str,
    value: str,
    *,
    shift: bool = False,
    ctrl: bool = False,
    alt: bool = False,
) -> None:
    keymap_item = keymap.keymap_items.new(idname, event_type, value, shift=shift, ctrl=ctrl, alt=alt)
    if hasattr(keymap_item.properties, "use_cursor_init"):
        keymap_item.properties.use_cursor_init = True
    _runtime_state.added_keymap_items.append(
        _AddedKeymapItem(_KeymapLocation(keyconfig_name, keymap.name), _get_keymap_item_signature(keymap_item))
    )


def _add_modal_keymap_item(
    keyconfig_name: str,
    keymap: bpy.types.KeyMap,
    propvalue: str,
    event_type: str,
    value: str,
) -> None:
    keymap_item = keymap.keymap_items.new_modal(propvalue, event_type, value)
    _runtime_state.added_keymap_items.append(
        _AddedKeymapItem(_KeymapLocation(keyconfig_name, keymap.name), _get_keymap_item_signature(keymap_item))
    )


def _remove_added_keymap_items() -> None:
    for added_item in reversed(_runtime_state.added_keymap_items):
        keymap = _get_runtime_keymap(added_item.location)
        if keymap is None:
            print(f"ZBrush Navigation: skipped removal; keymap not found: {added_item.location}")
            continue
        removed = _remove_first_matching_keymap_item(keymap, added_item.signature)
        if not removed:
            print(f"ZBrush Navigation: skipped removal; keymap item already gone: {added_item.location}")


def _remove_first_matching_keymap_item(keymap: bpy.types.KeyMap, signature: _KeymapItemSignature) -> bool:
    for keymap_item in reversed(list(keymap.keymap_items)):
        if _get_keymap_item_signature(keymap_item) == signature:
            keymap.keymap_items.remove(keymap_item)
            return True
    return False


def _set_first_matching_keymap_item_active(
    keymap: bpy.types.KeyMap,
    signature: _KeymapItemSignature,
    *,
    active: bool,
) -> bool:
    for keymap_item in reversed(list(keymap.keymap_items)):
        if keymap_item.active == active:
            continue
        if _get_keymap_item_signature(keymap_item) == signature:
            keymap_item.active = active
            return True
    return False


def _get_keymap_item_signature(keymap_item: bpy.types.KeyMapItem) -> _KeymapItemSignature:
    return _KeymapItemSignature(
        idname=keymap_item.idname,
        propvalue=getattr(keymap_item, "propvalue", "NONE"),
        type=keymap_item.type,
        value=keymap_item.value,
        any=bool(keymap_item.any),
        shift=bool(keymap_item.shift),
        ctrl=bool(keymap_item.ctrl),
        alt=bool(keymap_item.alt),
        oskey=bool(keymap_item.oskey),
        key_modifier=keymap_item.key_modifier,
        direction=keymap_item.direction,
        map_type=keymap_item.map_type,
    )


def _get_runtime_keymap(location: _KeymapLocation) -> bpy.types.KeyMap | None:
    keyconfig = getattr(bpy.context.window_manager.keyconfigs, location.keyconfig_name, None)
    if keyconfig is None:
        return None
    return _get_existing_keymap(keyconfig, location.keymap_name)


def _get_existing_keymap(keyconfig: bpy.types.KeyConfig, name: str) -> bpy.types.KeyMap | None:
    return keyconfig.keymaps.get(name)


def _get_or_create_keymap(
    keyconfig: bpy.types.KeyConfig,
    name: str,
    *,
    space_type: str = "EMPTY",
    region_type: str = "WINDOW",
    modal: bool = False,
) -> bpy.types.KeyMap:
    existing_keymap = _get_existing_keymap(keyconfig, name)
    if existing_keymap is not None:
        return existing_keymap
    return keyconfig.keymaps.new(name=name, space_type=space_type, region_type=region_type, modal=modal)


def _space_type_for_keymap(keymap_name: str) -> str:
    if keymap_name == VIEW3D_KEYMAP_NAME:
        return "VIEW_3D"
    return "EMPTY"


def _is_conflicting_right_mouse_item(keymap_item: bpy.types.KeyMapItem) -> bool:
    if keymap_item.type != "RIGHTMOUSE":
        return False
    if keymap_item.any:
        return True
    return _modifier_state(keymap_item) in RIGHT_MOUSE_TARGET_MODIFIERS


def _is_axis_snap_modal_item(keymap_item: bpy.types.KeyMapItem) -> bool:
    return getattr(keymap_item, "propvalue", None) in AXIS_SNAP_MODAL_VALUES


def _modifier_state(keymap_item: bpy.types.KeyMapItem) -> tuple[bool, bool, bool, bool]:
    return (bool(keymap_item.shift), bool(keymap_item.ctrl), bool(keymap_item.alt), bool(keymap_item.oskey))


def _navigation_mode_timer() -> float | None:
    if not _timer_enabled:
        return None
    synchronize_navigation_state()
    return TIMER_INTERVAL_SECONDS


@persistent
def _restore_on_load_pre(_dummy):
    if _runtime_state.applied:
        restore_zbrush_navigation()


def register():
    global _timer_enabled
    _timer_enabled = True
    if not bpy.app.timers.is_registered(_navigation_mode_timer):
        bpy.app.timers.register(_navigation_mode_timer, first_interval=TIMER_INTERVAL_SECONDS, persistent=True)
    if _restore_on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_restore_on_load_pre)


def unregister():
    global _timer_enabled
    _timer_enabled = False
    if bpy.app.timers.is_registered(_navigation_mode_timer):
        bpy.app.timers.unregister(_navigation_mode_timer)
    if _restore_on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_restore_on_load_pre)
    if _runtime_state.applied:
        restore_zbrush_navigation()