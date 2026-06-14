from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


ROOT = Path(__file__).resolve().parents[1]
ADDON_MODULE = ROOT.name
EPSILON = 0.0001


def main() -> int:
    sys.path.insert(0, str(ROOT.parent))
    bpy.ops.preferences.addon_enable(module=ADDON_MODULE)

    try:
        test_keymaps_are_addon_scoped()
        test_snap_keeps_projection()
        test_orbit_center_preserves_screen_offset()
        test_active_object_center()
    finally:
        bpy.ops.preferences.addon_disable(module=ADDON_MODULE)

    print("Blender regression checks passed")
    return 0


def test_keymaps_are_addon_scoped() -> None:
    import zbrush_navigation.functions.navigation_state as navigation_state

    keyconfigs = bpy.context.window_manager.keyconfigs
    user_keyconfig = keyconfigs.user
    legacy_sculpt_keymap = user_keyconfig.keymaps.new(name="Sculpt", space_type="EMPTY", region_type="WINDOW")
    legacy_sculpt_keymap.keymap_items.new("zbrush_navigation.zbrush_rotate_modal", "RIGHTMOUSE", "PRESS")
    legacy_sculpt_keymap.keymap_items.new("view3d.zoom", "RIGHTMOUSE", "PRESS", ctrl=True)

    navigation_state.apply_zbrush_navigation()
    addon_sculpt_keymap = keyconfigs.addon.keymaps.get("Sculpt")
    addon_view3d_keymap = keyconfigs.addon.keymaps.get("3D View")

    assert addon_sculpt_keymap is not None, "Missing add-on Sculpt keymap"
    assert addon_view3d_keymap is not None, "Missing add-on 3D View keymap"
    assert _has_keymap_item(addon_sculpt_keymap, "view3d.view_persportho", "P")
    assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.zbrush_rotate_modal", "RIGHTMOUSE")
    assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.zbrush_rotate_modal", "RIGHTMOUSE", shift=True)
    assert _has_keymap_item(addon_sculpt_keymap, "view3d.zoom", "RIGHTMOUSE", ctrl=True)
    assert _has_keymap_item(addon_sculpt_keymap, "view3d.move", "RIGHTMOUSE", alt=True)
    assert _has_keymap_item(addon_sculpt_keymap, "sculpt.brush_stroke", "LEFTMOUSE", alt=True, mode="INVERT")
    assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.mask_ctrl_click", "LEFTMOUSE", ctrl=True, value="CLICK")
    assert _has_keymap_item(
        addon_sculpt_keymap,
        "zbrush_navigation.mask_pen_input",
        "LEFTMOUSE",
        ctrl=True,
        float_value=1.0,
    )
    assert _has_keymap_item(
        addon_sculpt_keymap,
        "zbrush_navigation.mask_pen_input",
        "LEFTMOUSE",
        ctrl=True,
        alt=True,
        float_value=0.0,
    )
    assert _has_keymap_item(
        addon_sculpt_keymap,
        "sculpt.brush_stroke",
        "LEFTMOUSE",
        ctrl=True,
        value="CLICK_DRAG",
        mode="NORMAL",
        brush_toggle="MASK",
    )
    assert _has_keymap_item(
        addon_sculpt_keymap,
        "sculpt.brush_stroke",
        "LEFTMOUSE",
        ctrl=True,
        alt=True,
        value="CLICK_DRAG",
        mode="INVERT",
        brush_toggle="MASK",
    )
    assert not _has_user_plugin_items(user_keyconfig), "Legacy user keymap items were not cleaned"

    settings = bpy.context.window_manager.zbrush_navigation_settings
    settings.mask_input_mode = "LASSO"
    navigation_state.refresh_zbrush_navigation()
    addon_sculpt_keymap = keyconfigs.addon.keymaps.get("Sculpt")
    assert _has_keymap_item(
        addon_sculpt_keymap,
        "paint.mask_lasso_gesture",
        "LEFTMOUSE",
        ctrl=True,
        value="CLICK_DRAG",
        mode="VALUE",
        float_value=1.0,
    )
    assert _has_keymap_item(
        addon_sculpt_keymap,
        "paint.mask_lasso_gesture",
        "LEFTMOUSE",
        ctrl=True,
        alt=True,
        value="CLICK_DRAG",
        mode="VALUE",
        float_value=0.0,
    )
    assert not _has_keymap_item(
        addon_sculpt_keymap,
        "sculpt.brush_stroke",
        "LEFTMOUSE",
        ctrl=True,
        value="CLICK_DRAG",
        mode="NORMAL",
        brush_toggle="MASK",
    )

    navigation_state.restore_zbrush_navigation()
    assert not _has_runtime_navigation_items(addon_sculpt_keymap), "Runtime Sculpt keymap items were not removed"
    assert not _has_runtime_navigation_items(addon_view3d_keymap), "Runtime 3D View keymap items were not removed"


def test_snap_keeps_projection() -> None:
    from zbrush_navigation.functions.view_snap import get_view_direction, snap_region_3d_to_nearest_axis

    region_3d = _Region3D()
    region_3d.view_rotation = Quaternion((0.5, 0.5, 0.5, 0.5))
    region_3d.view_perspective = "PERSP"
    axis_view = snap_region_3d_to_nearest_axis(region_3d)
    assert region_3d.view_perspective == "PERSP"
    assert abs(get_view_direction(region_3d.view_rotation).dot(axis_view.direction) - 1.0) < EPSILON

    region_3d.view_rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
    region_3d.view_perspective = "ORTHO"
    snap_region_3d_to_nearest_axis(region_3d)
    assert region_3d.view_perspective == "ORTHO"


def test_orbit_center_preserves_screen_offset() -> None:
    from zbrush_navigation.operators.navigation_modal import _get_view_offset, _set_view_rotation_around_center

    region_3d = _Region3D()
    region_3d.view_rotation = Quaternion((1.0, 0.0, 0.0, 0.0))
    region_3d.view_location = Vector((1.0, 2.0, 3.0))
    center = Vector((4.0, 6.0, 8.0))
    original_offset = _get_view_offset(region_3d, center)

    _set_view_rotation_around_center(
        region_3d,
        center,
        original_offset,
        Quaternion(Vector((0.0, 0.0, 1.0)), 0.5),
    )

    preserved_offset = region_3d.view_rotation.inverted() @ (center - region_3d.view_location)
    assert (preserved_offset - original_offset).length < EPSILON
    assert (region_3d.view_location - center).length > EPSILON, "View was incorrectly moved to object center"


def test_active_object_center() -> None:
    from zbrush_navigation.operators.navigation_modal import _get_active_object_center

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2.0, location=(3.0, 4.0, 5.0))
    center = _get_active_object_center(bpy.context)
    assert (center - Vector((3.0, 4.0, 5.0))).length < EPSILON


def _has_keymap_item(
    keymap,
    idname: str,
    event_type: str,
    *,
    shift: bool = False,
    ctrl: bool = False,
    alt: bool = False,
    value: str = "PRESS",
    mode: str | None = None,
    brush_toggle: str | None = None,
    float_value: float | None = None,
) -> bool:
    for keymap_item in keymap.keymap_items:
        if keymap_item.idname != idname or keymap_item.type != event_type or keymap_item.value != value:
            continue
        if bool(keymap_item.shift) != shift or bool(keymap_item.ctrl) != ctrl or bool(keymap_item.alt) != alt:
            continue
        if mode is not None and getattr(keymap_item.properties, "mode", None) != mode:
            continue
        if brush_toggle is not None and getattr(keymap_item.properties, "brush_toggle", None) != brush_toggle:
            continue
        if float_value is not None:
            item_value = getattr(keymap_item.properties, "value", None)
            if item_value is None or abs(item_value - float_value) > EPSILON:
                continue
        return True
    return False


def _has_user_plugin_items(keyconfig) -> bool:
    for keymap in keyconfig.keymaps:
        if keymap.name not in {"Sculpt", "3D View"}:
            continue
        if any(keymap_item.idname.startswith("zbrush_navigation.") for keymap_item in keymap.keymap_items):
            return True
    return False


def _has_runtime_navigation_items(keymap) -> bool:
    runtime_idnames = {
        "zbrush_navigation.zbrush_rotate_modal",
        "zbrush_navigation.mask_ctrl_click",
        "zbrush_navigation.mask_pen_input",
        "paint.mask_lasso_gesture",
        "sculpt.brush_stroke",
        "view3d.zoom",
        "view3d.move",
    }
    return any(keymap_item.idname in runtime_idnames for keymap_item in keymap.keymap_items)


class _Region3D:
    view_rotation: Quaternion
    view_location: Vector
    view_perspective: str


if __name__ == "__main__":
    raise SystemExit(main())