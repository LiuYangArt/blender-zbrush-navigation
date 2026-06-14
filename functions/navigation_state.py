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
class _SerializedModalItem:
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
    active: bool


@dataclass(frozen=True)
class _ActiveStateSnapshot:
    location: _KeymapLocation
    signature: _KeymapItemSignature


@dataclass(frozen=True)
class _AddedKeymapItem:
    location: _KeymapLocation
    signature: _KeymapItemSignature


@dataclass(frozen=True)
class _CreatedKeymap:
    location: _KeymapLocation


@dataclass
class _RuntimeState:
    applied: bool = False
    original_emulate_3_button: bool | None = None
    active_snapshots: list[_ActiveStateSnapshot] = field(default_factory=list)
    added_keymap_items: list[_AddedKeymapItem] = field(default_factory=list)
    created_keymaps: list[_CreatedKeymap] = field(default_factory=list)
    rotate_modal_snapshot: list[_SerializedModalItem] | None = None


_runtime_state = _RuntimeState()
_static_added_keymap_items: list[_AddedKeymapItem] = []
_static_created_keymaps: list[_CreatedKeymap] = []
_timer_enabled = False
_status_message_token = 0


def format_settings_summary(settings) -> str:
    enabled = "enabled" if settings.enable_zbrush_navigation else "disabled"
    active = "active" if _runtime_state.applied else "inactive"
    return f"ZBrush Navigation is {enabled}; Sculpt override is {active}"


def register_static_sculpt_keymaps() -> None:
    if _static_added_keymap_items:
        return

    user_keyconfig = bpy.context.window_manager.keyconfigs.user
    if user_keyconfig is None:
        raise RuntimeError("Blender user keyconfig is not available")

    sculpt_keymap = _get_existing_keymap(user_keyconfig, SCULPT_KEYMAP_NAME)
    if sculpt_keymap is None:
        sculpt_keymap = user_keyconfig.keymaps.new(name=SCULPT_KEYMAP_NAME, space_type="EMPTY", region_type="WINDOW")
        _static_created_keymaps.append(_CreatedKeymap(_KeymapLocation("user", SCULPT_KEYMAP_NAME)))

    keymap_item = sculpt_keymap.keymap_items.new("view3d.view_persportho", "P", "PRESS")
    _static_added_keymap_items.append(
        _AddedKeymapItem(_KeymapLocation("user", sculpt_keymap.name), _get_keymap_item_signature(keymap_item))
    )


def unregister_static_sculpt_keymaps() -> None:
    for added_item in reversed(_static_added_keymap_items):
        keymap = _get_runtime_keymap(added_item.location)
        if keymap is None:
            print(f"ZBrush Navigation: skipped static removal; keymap not found: {added_item.location}")
            continue
        removed = _remove_first_matching_keymap_item(keymap, added_item.signature)
        if not removed:
            print(f"ZBrush Navigation: skipped static removal; keymap item already gone: {added_item.location}")
    _static_added_keymap_items.clear()

    for created_keymap in reversed(_static_created_keymaps):
        keyconfig = getattr(bpy.context.window_manager.keyconfigs, created_keymap.location.keyconfig_name, None)
        if keyconfig is None:
            continue
        keymap = _get_existing_keymap(keyconfig, created_keymap.location.keymap_name)
        if keymap is not None and len(keymap.keymap_items) == 0:
            keyconfig.keymaps.remove(keymap)
    _static_created_keymaps.clear()


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
    _restore_rotate_modal_keymap()
    _remove_added_keymap_items()
    _restore_disabled_keymap_items()
    _remove_empty_created_keymaps()
    if _runtime_state.original_emulate_3_button is not None:
        preferences.inputs.use_mouse_emulate_3_button = _runtime_state.original_emulate_3_button
    _show_status_message("ZBrush Navigation: original navigation restored")
    _reset_runtime_state()


def _reset_runtime_state() -> None:
    _runtime_state.applied = False
    _runtime_state.original_emulate_3_button = None
    _runtime_state.active_snapshots.clear()
    _runtime_state.added_keymap_items.clear()
    _runtime_state.created_keymaps.clear()
    _runtime_state.rotate_modal_snapshot = None


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
    keyconfig_name = "user"
    keyconfig = getattr(bpy.context.window_manager.keyconfigs, keyconfig_name, None)
    if keyconfig is None:
        return

    for keymap in _iter_navigation_conflict_keymaps(keyconfig):
        for keymap_item in keymap.keymap_items:
            if _is_conflicting_right_mouse_item(keymap_item):
                _disable_keymap_item(keyconfig_name, keymap, keymap_item)


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
        keymap = _get_or_create_keymap("user", user_keyconfig, keymap_name, space_type=_space_type_for_keymap(keymap_name))
        _add_keymap_item("user", keymap, "view3d.rotate", "RIGHTMOUSE", "PRESS")
        _add_keymap_item("user", keymap, "view3d.zoom", "RIGHTMOUSE", "PRESS", ctrl=True)
        _add_keymap_item("user", keymap, "view3d.move", "RIGHTMOUSE", "PRESS", alt=True)
        if keymap_name == SCULPT_KEYMAP_NAME:
            _add_keymap_item(
                "user",
                keymap,
                "zbrush_navigation.snap_view_to_nearest_axis",
                "RIGHTMOUSE",
                "PRESS",
                shift=True,
            )

    rotate_modal_keymap = _get_existing_keymap(user_keyconfig, VIEW3D_ROTATE_MODAL_KEYMAP_NAME)
    if rotate_modal_keymap is not None and _has_axis_snap_modal_items(rotate_modal_keymap):
        original_items = _serialize_modal_keymap(rotate_modal_keymap)
        _runtime_state.rotate_modal_snapshot = original_items
        _replace_modal_keymap_items(rotate_modal_keymap, _retarget_axis_snap_modal_items(original_items))
    else:
        print("ZBrush Navigation: skipped View3D Rotate Modal retarget; no existing Axis Snap entries")


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


AXIS_SNAP_MODAL_PROPVALUES = {"AXIS_SNAP_ENABLE", "AXIS_SNAP_DISABLE"}
AXIS_SNAP_MODAL_KEY_TYPES = ("LEFT_SHIFT", "RIGHT_SHIFT")


def _has_axis_snap_modal_items(keymap: bpy.types.KeyMap) -> bool:
    return any(keymap_item.propvalue in AXIS_SNAP_MODAL_PROPVALUES for keymap_item in keymap.keymap_items)


def _retarget_axis_snap_modal_items(items: list[_SerializedModalItem]) -> list[_SerializedModalItem]:
    snap_indexes = {"AXIS_SNAP_ENABLE": 0, "AXIS_SNAP_DISABLE": 0}
    retargeted_items = []
    for item in items:
        if item.propvalue not in AXIS_SNAP_MODAL_PROPVALUES:
            retargeted_items.append(item)
            continue
        key_type = AXIS_SNAP_MODAL_KEY_TYPES[snap_indexes[item.propvalue] % len(AXIS_SNAP_MODAL_KEY_TYPES)]
        snap_indexes[item.propvalue] += 1
        value = "PRESS" if item.propvalue == "AXIS_SNAP_ENABLE" else "RELEASE"
        retargeted_items.append(
            _SerializedModalItem(
                propvalue=item.propvalue,
                type=key_type,
                value=value,
                any=False,
                shift=False,
                ctrl=False,
                alt=False,
                oskey=False,
                key_modifier="NONE",
                direction="ANY",
                active=True,
            )
        )
    return retargeted_items


def _serialize_modal_keymap(keymap: bpy.types.KeyMap) -> list[_SerializedModalItem]:
    return [_serialize_modal_keymap_item(keymap_item) for keymap_item in keymap.keymap_items]


def _serialize_modal_keymap_item(keymap_item: bpy.types.KeyMapItem) -> _SerializedModalItem:
    return _SerializedModalItem(
        propvalue=keymap_item.propvalue,
        type=keymap_item.type,
        value=keymap_item.value,
        any=bool(keymap_item.any),
        shift=bool(keymap_item.shift),
        ctrl=bool(keymap_item.ctrl),
        alt=bool(keymap_item.alt),
        oskey=bool(keymap_item.oskey),
        key_modifier=keymap_item.key_modifier,
        direction=keymap_item.direction,
        active=bool(keymap_item.active),
    )


def _restore_rotate_modal_keymap() -> None:
    snapshot = _runtime_state.rotate_modal_snapshot
    if snapshot is None:
        return
    user_keyconfig = bpy.context.window_manager.keyconfigs.user
    keymap = _get_existing_keymap(user_keyconfig, VIEW3D_ROTATE_MODAL_KEYMAP_NAME)
    if keymap is None:
        print("ZBrush Navigation: skipped rotate modal restore; keymap not found")
        return
    _replace_modal_keymap_items(keymap, snapshot)


def _remove_added_keymap_items() -> None:
    for added_item in reversed(_runtime_state.added_keymap_items):
        keymap = _get_runtime_keymap(added_item.location)
        if keymap is None:
            print(f"ZBrush Navigation: skipped removal; keymap not found: {added_item.location}")
            continue
        removed = _remove_first_matching_keymap_item(keymap, added_item.signature)
        if not removed:
            print(f"ZBrush Navigation: skipped removal; keymap item already gone: {added_item.location}")


def _remove_empty_created_keymaps() -> None:
    for created_keymap in reversed(_runtime_state.created_keymaps):
        if created_keymap.location.keymap_name == VIEW3D_ROTATE_MODAL_KEYMAP_NAME:
            continue
        keyconfig = getattr(bpy.context.window_manager.keyconfigs, created_keymap.location.keyconfig_name, None)
        if keyconfig is None:
            continue
        keymap = _get_existing_keymap(keyconfig, created_keymap.location.keymap_name)
        if keymap is None or len(keymap.keymap_items) != 0:
            continue
        keyconfig.keymaps.remove(keymap)


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


def _replace_modal_keymap_items(keymap: bpy.types.KeyMap, items: list[_SerializedModalItem]) -> None:
    for keymap_item in reversed(list(keymap.keymap_items)):
        keymap.keymap_items.remove(keymap_item)
    for item in items:
        _add_serialized_modal_keymap_item(keymap, item)


def _add_serialized_modal_keymap_item(keymap: bpy.types.KeyMap, item: _SerializedModalItem) -> bpy.types.KeyMapItem:
    keymap_item = keymap.keymap_items.new_modal(
        item.propvalue,
        item.type,
        item.value,
        any=item.any,
        shift=item.shift,
        ctrl=item.ctrl,
        alt=item.alt,
        oskey=item.oskey,
        key_modifier=item.key_modifier,
        direction=item.direction,
    )
    keymap_item.active = item.active
    return keymap_item


def _get_existing_keymap(keyconfig: bpy.types.KeyConfig, name: str) -> bpy.types.KeyMap | None:
    return keyconfig.keymaps.get(name)


def _get_or_create_keymap(
    keyconfig_name: str,
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
    keymap = keyconfig.keymaps.new(name=name, space_type=space_type, region_type=region_type, modal=modal)
    _runtime_state.created_keymaps.append(_CreatedKeymap(_KeymapLocation(keyconfig_name, name)))
    return keymap


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
    register_static_sculpt_keymaps()
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
    unregister_static_sculpt_keymaps()