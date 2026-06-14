from __future__ import annotations

from dataclasses import dataclass, field

import bpy
from bpy.app.handlers import persistent


TIMER_INTERVAL_SECONDS = 0.25
VIEW3D_KEYMAP_NAME = "3D View"
SCULPT_KEYMAP_NAME = "Sculpt"
NAVIGATION_KEYMAP_NAMES = (VIEW3D_KEYMAP_NAME, SCULPT_KEYMAP_NAME)
ROTATE_MODAL_KEYMAP_NAME = "View3D Rotate Modal"
ROTATE_MODAL_AXIS_SNAP_PROPVALUES = {"AXIS_SNAP_ENABLE", "AXIS_SNAP_DISABLE"}
SHIFT_ROTATE_MODAL_AXIS_SNAP_ITEMS = (
    ("AXIS_SNAP_ENABLE", "LEFT_SHIFT", "PRESS"),
    ("AXIS_SNAP_DISABLE", "LEFT_SHIFT", "RELEASE"),
    ("AXIS_SNAP_ENABLE", "RIGHT_SHIFT", "PRESS"),
    ("AXIS_SNAP_DISABLE", "RIGHT_SHIFT", "RELEASE"),
)
STATUS_MESSAGE_DURATION_SECONDS = 2.5
LEGACY_USER_KEYMAP_IDNAMES = {
    "zbrush_navigation.zbrush_rotate_modal",
    "zbrush_navigation.snap_view_to_nearest_axis",
    "view3d.rotate",
    "view3d.zoom",
    "view3d.move",
    "view3d.view_persportho",
}
LEGACY_RIGHT_MOUSE_TARGET_MODIFIERS = {
    (False, False, False, False),
    (False, True, False, False),
    (False, False, True, False),
    (True, False, False, False),
}


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
    mode: str | None
    brush_toggle: str | None
    float_value: float | None


@dataclass(frozen=True)
class _AddedKeymapItem:
    location: _KeymapLocation
    signature: _KeymapItemSignature


@dataclass(frozen=True)
class _CreatedKeymap:
    location: _KeymapLocation


@dataclass(frozen=True)
class _ModalKeymapItemSnapshot:
    signature: _KeymapItemSignature
    active: bool


@dataclass
class _RuntimeState:
    applied: bool = False
    original_emulate_3_button: bool | None = None
    original_use_rotate_around_active: bool | None = None
    added_keymap_items: list[_AddedKeymapItem] = field(default_factory=list)
    created_keymaps: list[_CreatedKeymap] = field(default_factory=list)
    mask_input_mode: str | None = None
    use_zbrush_style_rotate: bool | None = None
    original_rotate_modal_axis_snap_items: list[_ModalKeymapItemSnapshot] | None = None


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

    _remove_legacy_user_keymap_items()
    addon_keyconfig = _get_addon_keyconfig()
    sculpt_keymap = _get_or_create_static_keymap(addon_keyconfig, SCULPT_KEYMAP_NAME)
    keymap_item = sculpt_keymap.keymap_items.new("view3d.view_persportho", "P", "PRESS")
    _static_added_keymap_items.append(
        _AddedKeymapItem(_KeymapLocation("addon", sculpt_keymap.name), _get_keymap_item_signature(keymap_item))
    )


def unregister_static_sculpt_keymaps() -> None:
    _remove_added_items(_static_added_keymap_items, "static")
    _static_added_keymap_items.clear()
    _remove_empty_created_keymaps(_static_created_keymaps)
    _static_created_keymaps.clear()


def is_sculpt_mode_active() -> bool:
    return getattr(bpy.context, "mode", None) == "SCULPT"


def synchronize_navigation_state() -> None:
    settings = getattr(bpy.context.window_manager, "zbrush_navigation_settings", None)
    should_apply = bool(settings and settings.enable_zbrush_navigation and is_sculpt_mode_active())
    if should_apply and not _runtime_state.applied:
        apply_zbrush_navigation()
    elif should_apply and _runtime_state.applied:
        refresh_zbrush_navigation()
    elif not should_apply and _runtime_state.applied:
        restore_zbrush_navigation()


def apply_zbrush_navigation() -> None:
    if _runtime_state.applied:
        return

    preferences = bpy.context.preferences
    _runtime_state.original_emulate_3_button = preferences.inputs.use_mouse_emulate_3_button
    _runtime_state.original_use_rotate_around_active = preferences.inputs.use_rotate_around_active

    try:
        _remove_legacy_user_keymap_items()
        _add_zbrush_keymap_items()
        _runtime_state.mask_input_mode = _get_mask_input_mode()
        _runtime_state.use_zbrush_style_rotate = _use_zbrush_style_rotate()
        preferences.inputs.use_mouse_emulate_3_button = False
        _sync_rotate_around_active_preference(_runtime_state.use_zbrush_style_rotate)
        _sync_rotate_modal_axis_snap_keymap(_runtime_state.use_zbrush_style_rotate)
        _runtime_state.applied = True
        _show_status_message("ZBrush Navigation: Sculpt Mode override enabled")
    except Exception as error:
        restore_zbrush_navigation()
        raise RuntimeError("Failed to apply ZBrush Navigation sculpt keymaps") from error


def refresh_zbrush_navigation() -> None:
    if not _runtime_state.applied:
        return

    mask_input_mode = _get_mask_input_mode()
    use_zbrush_style_rotate = _use_zbrush_style_rotate()
    if (
        mask_input_mode == _runtime_state.mask_input_mode
        and use_zbrush_style_rotate == _runtime_state.use_zbrush_style_rotate
    ):
        return

    _remove_added_items(_runtime_state.added_keymap_items, "runtime")
    _runtime_state.added_keymap_items.clear()
    _remove_empty_created_keymaps(_runtime_state.created_keymaps)
    _runtime_state.created_keymaps.clear()
    _sync_rotate_around_active_preference(use_zbrush_style_rotate)
    _sync_rotate_modal_axis_snap_keymap(use_zbrush_style_rotate)
    _add_zbrush_keymap_items()
    _runtime_state.mask_input_mode = mask_input_mode
    _runtime_state.use_zbrush_style_rotate = use_zbrush_style_rotate

def restore_zbrush_navigation() -> None:
    preferences = bpy.context.preferences
    _remove_added_items(_runtime_state.added_keymap_items, "runtime")
    _remove_empty_created_keymaps(_runtime_state.created_keymaps)
    if _runtime_state.original_emulate_3_button is not None:
        preferences.inputs.use_mouse_emulate_3_button = _runtime_state.original_emulate_3_button
    if _runtime_state.original_use_rotate_around_active is not None:
        preferences.inputs.use_rotate_around_active = _runtime_state.original_use_rotate_around_active
    _restore_rotate_modal_axis_snap_keymap()
    _show_status_message("ZBrush Navigation: original navigation restored")
    _reset_runtime_state()


def _reset_runtime_state() -> None:
    _runtime_state.applied = False
    _runtime_state.original_emulate_3_button = None
    _runtime_state.original_use_rotate_around_active = None
    _runtime_state.added_keymap_items.clear()
    _runtime_state.created_keymaps.clear()
    _runtime_state.mask_input_mode = None
    _runtime_state.use_zbrush_style_rotate = None
    _runtime_state.original_rotate_modal_axis_snap_items = None



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


def _add_zbrush_keymap_items() -> None:
    addon_keyconfig = _get_addon_keyconfig()
    use_zbrush_style_rotate = _use_zbrush_style_rotate()
    rotate_operator = "zbrush_navigation.zbrush_rotate_modal" if use_zbrush_style_rotate else "view3d.rotate"
    snap_operator = (
        "zbrush_navigation.zbrush_rotate_modal"
        if use_zbrush_style_rotate
        else "zbrush_navigation.snap_view_to_nearest_axis"
    )

    for keymap_name in NAVIGATION_KEYMAP_NAMES:
        keymap = _get_or_create_runtime_keymap(addon_keyconfig, keymap_name, space_type=_space_type_for_keymap(keymap_name))
        _add_keymap_item("addon", keymap, rotate_operator, "RIGHTMOUSE", "PRESS")
        _add_keymap_item("addon", keymap, "view3d.zoom", "RIGHTMOUSE", "PRESS", ctrl=True)
        _add_keymap_item("addon", keymap, "view3d.move", "RIGHTMOUSE", "PRESS", alt=True)
        if keymap_name == SCULPT_KEYMAP_NAME:
            _add_keymap_item("addon", keymap, snap_operator, "RIGHTMOUSE", "PRESS", shift=True)
            _add_keymap_item("addon", keymap, "zbrush_navigation.multires_existing_level_up", "D", "PRESS")
            _add_keymap_item("addon", keymap, "zbrush_navigation.multires_level_up", "D", "PRESS", ctrl=True)
            _add_keymap_item("addon", keymap, "zbrush_navigation.multires_level_down", "D", "PRESS", shift=True)
            _add_keymap_item(
                "addon",
                keymap,
                "sculpt.brush_stroke",
                "LEFTMOUSE",
                "PRESS",
                alt=True,
                properties={"mode": "INVERT"},
            )
            _add_mask_input_keymap_items(keymap, _get_mask_input_mode())


def _add_mask_input_keymap_items(keymap: bpy.types.KeyMap, mask_input_mode: str) -> None:
    _add_keymap_item(
        "addon",
        keymap,
        "zbrush_navigation.mask_pen_input",
        "LEFTMOUSE",
        "PRESS",
        ctrl=True,
        properties={"value": 1.0},
    )
    _add_keymap_item(
        "addon",
        keymap,
        "zbrush_navigation.mask_pen_input",
        "LEFTMOUSE",
        "PRESS",
        ctrl=True,
        alt=True,
        properties={"value": 0.0},
    )

    if mask_input_mode == "PEN":
        _add_keymap_item(
            "addon",
            keymap,
            "sculpt.brush_stroke",
            "LEFTMOUSE",
            "CLICK_DRAG",
            ctrl=True,
            properties={"mode": "NORMAL", "brush_toggle": "MASK"},
        )
        _add_keymap_item(
            "addon",
            keymap,
            "sculpt.brush_stroke",
            "LEFTMOUSE",
            "CLICK_DRAG",
            ctrl=True,
            alt=True,
            properties={"mode": "INVERT", "brush_toggle": "MASK"},
        )
        return

    if mask_input_mode == "LASSO":
        _add_keymap_item(
            "addon",
            keymap,
            "paint.mask_lasso_gesture",
            "LEFTMOUSE",
            "CLICK_DRAG",
            ctrl=True,
            properties={"mode": "VALUE", "value": 1.0},
        )
        _add_keymap_item(
            "addon",
            keymap,
            "paint.mask_lasso_gesture",
            "LEFTMOUSE",
            "CLICK_DRAG",
            ctrl=True,
            alt=True,
            properties={"mode": "VALUE", "value": 0.0},
        )
        return

    raise RuntimeError(f"Unsupported mask input mode: {mask_input_mode}")


def _get_mask_input_mode() -> str:
    settings = getattr(bpy.context.window_manager, "zbrush_navigation_settings", None)
    if settings is None:
        return "PEN"
    return settings.mask_input_mode


def _use_zbrush_style_rotate() -> bool:
    addon = bpy.context.preferences.addons.get(__package__.rsplit(".", 1)[0])
    if addon is None:
        raise RuntimeError("Cannot find ZBrush Navigation add-on preferences")
    return addon.preferences.use_zbrush_style_rotate


def _sync_rotate_around_active_preference(use_zbrush_style_rotate: bool) -> None:
    if _runtime_state.original_use_rotate_around_active is None:
        raise RuntimeError("Cannot sync rotate-around-active before original preference is recorded")

    bpy.context.preferences.inputs.use_rotate_around_active = (
        _runtime_state.original_use_rotate_around_active if use_zbrush_style_rotate else True
    )


def _sync_rotate_modal_axis_snap_keymap(use_zbrush_style_rotate: bool) -> None:
    if use_zbrush_style_rotate:
        _restore_rotate_modal_axis_snap_keymap()
        return

    user_keyconfig = bpy.context.window_manager.keyconfigs.user
    if user_keyconfig is None:
        raise RuntimeError("Blender user keyconfig is not available")

    keymap = user_keyconfig.keymaps.get(ROTATE_MODAL_KEYMAP_NAME)
    if keymap is None:
        return

    axis_snap_items = [
        keymap_item
        for keymap_item in keymap.keymap_items
        if keymap_item.propvalue in ROTATE_MODAL_AXIS_SNAP_PROPVALUES
    ]
    if not axis_snap_items:
        return

    if _runtime_state.original_rotate_modal_axis_snap_items is None:
        _runtime_state.original_rotate_modal_axis_snap_items = [
            _ModalKeymapItemSnapshot(_get_keymap_item_signature(keymap_item), keymap_item.active)
            for keymap_item in axis_snap_items
        ]

    _remove_rotate_modal_axis_snap_items(keymap)
    for propvalue, event_type, value in SHIFT_ROTATE_MODAL_AXIS_SNAP_ITEMS:
        keymap.keymap_items.new_modal(propvalue, event_type, value)


def _restore_rotate_modal_axis_snap_keymap() -> None:
    snapshots = _runtime_state.original_rotate_modal_axis_snap_items
    if snapshots is None:
        return

    user_keyconfig = bpy.context.window_manager.keyconfigs.user
    if user_keyconfig is None:
        raise RuntimeError("Blender user keyconfig is not available")

    keymap = user_keyconfig.keymaps.get(ROTATE_MODAL_KEYMAP_NAME)
    if keymap is None:
        raise RuntimeError(f"Cannot restore missing keymap: {ROTATE_MODAL_KEYMAP_NAME}")

    _remove_rotate_modal_axis_snap_items(keymap)
    for snapshot in snapshots:
        keymap_item = keymap.keymap_items.new_modal(
            snapshot.signature.propvalue,
            snapshot.signature.type,
            snapshot.signature.value,
            any=snapshot.signature.any,
            shift=snapshot.signature.shift,
            ctrl=snapshot.signature.ctrl,
            alt=snapshot.signature.alt,
            oskey=snapshot.signature.oskey,
            key_modifier=snapshot.signature.key_modifier,
            direction=snapshot.signature.direction,
        )
        keymap_item.active = snapshot.active




def _remove_rotate_modal_axis_snap_items(keymap: bpy.types.KeyMap) -> None:
    for keymap_item in reversed(list(keymap.keymap_items)):
        if keymap_item.propvalue in ROTATE_MODAL_AXIS_SNAP_PROPVALUES:
            keymap.keymap_items.remove(keymap_item)



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
    properties: dict[str, object] | None = None,
    store: list[_AddedKeymapItem] | None = None,
) -> None:
    keymap_item = keymap.keymap_items.new(idname, event_type, value, shift=shift, ctrl=ctrl, alt=alt)
    if hasattr(keymap_item.properties, "use_cursor_init"):
        keymap_item.properties.use_cursor_init = True
    if properties is not None:
        _set_keymap_item_properties(keymap_item, properties)
    target_store = _runtime_state.added_keymap_items if store is None else store
    target_store.append(
        _AddedKeymapItem(_KeymapLocation(keyconfig_name, keymap.name), _get_keymap_item_signature(keymap_item))
    )


def _set_keymap_item_properties(keymap_item: bpy.types.KeyMapItem, properties: dict[str, object]) -> None:
    for name, value in properties.items():
        if not hasattr(keymap_item.properties, name):
            raise RuntimeError(f"Keymap item {keymap_item.idname} has no property {name}")
        setattr(keymap_item.properties, name, value)


def _remove_added_items(added_items: list[_AddedKeymapItem], label: str) -> None:
    for added_item in reversed(added_items):
        keymap = _get_runtime_keymap(added_item.location)
        if keymap is None:
            print(f"ZBrush Navigation: skipped {label} removal; keymap not found: {added_item.location}")
            continue
        removed = _remove_first_matching_keymap_item(keymap, added_item.signature)
        if not removed:
            print(f"ZBrush Navigation: skipped {label} removal; keymap item already gone: {added_item.location}")


def _remove_legacy_user_keymap_items() -> None:
    user_keyconfig = bpy.context.window_manager.keyconfigs.user
    if user_keyconfig is None:
        return

    empty_legacy_keymaps = []
    for keymap in _iter_legacy_user_keymaps(user_keyconfig):
        for keymap_item in reversed(list(keymap.keymap_items)):
            if _is_legacy_plugin_keymap_item(keymap_item):
                keymap.keymap_items.remove(keymap_item)
                continue
            if _is_legacy_disabled_right_mouse_item(keymap_item):
                keymap_item.active = True
        if keymap.name in NAVIGATION_KEYMAP_NAMES and len(keymap.keymap_items) == 0:
            empty_legacy_keymaps.append(keymap)

    for keymap in empty_legacy_keymaps:
        user_keyconfig.keymaps.remove(keymap)


def _iter_legacy_user_keymaps(keyconfig: bpy.types.KeyConfig):
    for keymap in keyconfig.keymaps:
        if keymap.name in NAVIGATION_KEYMAP_NAMES or keymap.name.startswith("3D View Tool: Sculpt"):
            yield keymap


def _is_legacy_plugin_keymap_item(keymap_item: bpy.types.KeyMapItem) -> bool:
    if keymap_item.idname.startswith("zbrush_navigation."):
        return True
    if keymap_item.idname not in LEGACY_USER_KEYMAP_IDNAMES:
        return False
    if keymap_item.idname == "view3d.view_persportho":
        return keymap_item.type == "P" and keymap_item.value == "PRESS"
    if keymap_item.type != "RIGHTMOUSE" or keymap_item.value != "PRESS":
        return False
    return _modifier_state(keymap_item) in LEGACY_RIGHT_MOUSE_TARGET_MODIFIERS


def _is_legacy_disabled_right_mouse_item(keymap_item: bpy.types.KeyMapItem) -> bool:
    if keymap_item.active or keymap_item.type != "RIGHTMOUSE":
        return False
    if keymap_item.any:
        return True
    return _modifier_state(keymap_item) in LEGACY_RIGHT_MOUSE_TARGET_MODIFIERS


def _remove_empty_created_keymaps(created_keymaps: list[_CreatedKeymap]) -> None:
    for created_keymap in reversed(created_keymaps):
        keyconfig = getattr(bpy.context.window_manager.keyconfigs, created_keymap.location.keyconfig_name, None)
        if keyconfig is None:
            continue
        keymap = _get_existing_keymap(keyconfig, created_keymap.location.keymap_name)
        if keymap is not None and len(keymap.keymap_items) == 0:
            keyconfig.keymaps.remove(keymap)


def _remove_first_matching_keymap_item(keymap: bpy.types.KeyMap, signature: _KeymapItemSignature) -> bool:
    for keymap_item in reversed(list(keymap.keymap_items)):
        if _get_keymap_item_signature(keymap_item) == signature:
            keymap.keymap_items.remove(keymap_item)
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
        mode=getattr(keymap_item.properties, "mode", None),
        brush_toggle=getattr(keymap_item.properties, "brush_toggle", None),
        float_value=getattr(keymap_item.properties, "value", None) if hasattr(keymap_item.properties, "value") else None,
    )


def _get_runtime_keymap(location: _KeymapLocation) -> bpy.types.KeyMap | None:
    keyconfig = getattr(bpy.context.window_manager.keyconfigs, location.keyconfig_name, None)
    if keyconfig is None:
        return None
    return _get_existing_keymap(keyconfig, location.keymap_name)


def _get_addon_keyconfig() -> bpy.types.KeyConfig:
    addon_keyconfig = bpy.context.window_manager.keyconfigs.addon
    if addon_keyconfig is None:
        raise RuntimeError("Blender add-on keyconfig is not available")
    return addon_keyconfig


def _get_existing_keymap(keyconfig: bpy.types.KeyConfig, name: str) -> bpy.types.KeyMap | None:
    return keyconfig.keymaps.get(name)


def _get_or_create_runtime_keymap(
    keyconfig: bpy.types.KeyConfig,
    name: str,
    *,
    space_type: str = "EMPTY",
    region_type: str = "WINDOW",
) -> bpy.types.KeyMap:
    keymap = _get_or_create_keymap(keyconfig, name, space_type=space_type, region_type=region_type)
    if len(keymap.keymap_items) == 0:
        _runtime_state.created_keymaps.append(_CreatedKeymap(_KeymapLocation("addon", name)))
    return keymap


def _get_or_create_static_keymap(keyconfig: bpy.types.KeyConfig, name: str) -> bpy.types.KeyMap:
    keymap = _get_or_create_keymap(keyconfig, name)
    if len(keymap.keymap_items) == 0:
        _static_created_keymaps.append(_CreatedKeymap(_KeymapLocation("addon", name)))
    return keymap


def _get_or_create_keymap(
    keyconfig: bpy.types.KeyConfig,
    name: str,
    *,
    space_type: str = "EMPTY",
    region_type: str = "WINDOW",
) -> bpy.types.KeyMap:
    existing_keymap = _get_existing_keymap(keyconfig, name)
    if existing_keymap is not None:
        return existing_keymap
    return keyconfig.keymaps.new(name=name, space_type=space_type, region_type=region_type)


def _space_type_for_keymap(keymap_name: str) -> str:
    if keymap_name == VIEW3D_KEYMAP_NAME:
        return "VIEW_3D"
    return "EMPTY"


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