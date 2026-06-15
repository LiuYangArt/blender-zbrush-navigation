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
        test_sculpt_mode_addon_disable_restores_navigation()
        test_snap_keeps_projection()
        test_multires_level_operators()
        test_empty_drag_voxel_remesh_helpers()
        test_mask_drag_value_uses_release_alt_state()
        test_mask_selection_overlay_helpers()
        test_faceset_helpers()
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
    addon_preferences = _get_addon_preferences()
    input_preferences = bpy.context.preferences.inputs
    original_emulate_3_button = input_preferences.use_mouse_emulate_3_button
    original_rotate_around_active = input_preferences.use_rotate_around_active

    try:
        addon_preferences.use_zbrush_style_rotate = False
        assert addon_preferences.mask_drag_threshold_pixels == 10.0
        input_preferences.use_mouse_emulate_3_button = True
        input_preferences.use_rotate_around_active = False
        legacy_sculpt_keymap = user_keyconfig.keymaps.new(name="Sculpt", space_type="EMPTY", region_type="WINDOW")
        legacy_sculpt_keymap.keymap_items.new("zbrush_navigation.zbrush_rotate_modal", "RIGHTMOUSE", "PRESS")
        legacy_sculpt_keymap.keymap_items.new("view3d.zoom", "RIGHTMOUSE", "PRESS", ctrl=True)
        legacy_sculpt_keymap.keymap_items.new("wm.call_menu", "RIGHTMOUSE", "PRESS")
        rotate_modal_keymap = _get_or_create_user_rotate_modal_keymap(user_keyconfig)
        _remove_rotate_modal_axis_snap_items(rotate_modal_keymap)
        rotate_modal_keymap.keymap_items.new_modal("AXIS_SNAP_ENABLE", "LEFT_ALT", "PRESS")
        rotate_modal_keymap.keymap_items.new_modal("AXIS_SNAP_DISABLE", "LEFT_ALT", "RELEASE")

        navigation_state.apply_zbrush_navigation()
        settings = bpy.context.window_manager.zbrush_navigation_settings
        assert settings.pen_outside_drag_mode == "LASSO"
        assert settings.enable_empty_drag_voxel_remesh is False
        assert settings.faceset_gesture == "BOX"
        assert settings.faceset_front_faces_only is False
        assert settings.faceset_line_limit_to_segment is False
        assert input_preferences.use_mouse_emulate_3_button is False
        assert input_preferences.use_rotate_around_active is True
        addon_sculpt_keymap = keyconfigs.addon.keymaps.get("Sculpt")
        addon_view3d_keymap = keyconfigs.addon.keymaps.get("3D View")

        assert addon_sculpt_keymap is not None, "Missing add-on Sculpt keymap"
        assert addon_view3d_keymap is not None, "Missing add-on 3D View keymap"
        assert _has_keymap_item(addon_sculpt_keymap, "view3d.view_persportho", "P")
        assert _has_keymap_item(addon_sculpt_keymap, "view3d.rotate", "RIGHTMOUSE", value="CLICK_DRAG")
        assert not _has_keymap_item(addon_sculpt_keymap, "view3d.rotate", "RIGHTMOUSE")
        assert not _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.zbrush_rotate_modal", "RIGHTMOUSE")
        assert _has_keymap_item(legacy_sculpt_keymap, "wm.call_menu", "RIGHTMOUSE")
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.snap_view_to_nearest_axis", "RIGHTMOUSE", shift=True)
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.multires_existing_level_up", "D")
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.multires_level_up", "D", ctrl=True)
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.multires_level_down", "D", shift=True)
        assert _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_ENABLE", "LEFT_SHIFT", "PRESS")
        assert _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_DISABLE", "LEFT_SHIFT", "RELEASE")
        assert _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_ENABLE", "RIGHT_SHIFT", "PRESS")
        assert _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_DISABLE", "RIGHT_SHIFT", "RELEASE")
        assert not _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_ENABLE", "LEFT_ALT", "PRESS")
        assert _has_keymap_item(addon_sculpt_keymap, "view3d.zoom", "RIGHTMOUSE", ctrl=True)
        assert _has_keymap_item(addon_sculpt_keymap, "view3d.move", "RIGHTMOUSE", alt=True)
        assert _has_keymap_item(addon_sculpt_keymap, "sculpt.brush_stroke", "LEFTMOUSE", alt=True, mode="INVERT")
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.faceset_polygroup_input", "LEFTMOUSE", shift=True, ctrl=True)
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.faceset_polygroup_input", "LEFTMOUSE", shift=True, ctrl=True, alt=True)
        assert not _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.mask_ctrl_click", "LEFTMOUSE", ctrl=True, value="CLICK")
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.mask_pen_input", "LEFTMOUSE", ctrl=True, float_value=1.0)
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
            "zbrush_navigation.mask_filter_click",
            "LEFTMOUSE",
            ctrl=True,
            value="CLICK",
            float_value=1.0,
        )
        assert _has_keymap_item(
            addon_sculpt_keymap,
            "zbrush_navigation.mask_filter_click",
            "LEFTMOUSE",
            ctrl=True,
            alt=True,
            value="CLICK",
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

        settings.mask_input_mode = "LASSO"
        navigation_state.refresh_zbrush_navigation()
        addon_sculpt_keymap = keyconfigs.addon.keymaps.get("Sculpt")
        assert _has_keymap_item(addon_sculpt_keymap, "view3d.rotate", "RIGHTMOUSE", value="CLICK_DRAG")
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.faceset_polygroup_input", "LEFTMOUSE", shift=True, ctrl=True)
        assert not _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.mask_pen_input", "LEFTMOUSE", ctrl=True, float_value=1.0)
        assert not _has_keymap_item(
            addon_sculpt_keymap,
            "zbrush_navigation.mask_filter_click",
            "LEFTMOUSE",
            ctrl=True,
            value="CLICK",
            float_value=1.0,
        )
        assert _has_keymap_item(
            addon_sculpt_keymap,
            "zbrush_navigation.mask_lasso_input",
            "LEFTMOUSE",
            ctrl=True,
            float_value=1.0,
        )
        assert _has_keymap_item(
            addon_sculpt_keymap,
            "zbrush_navigation.mask_lasso_input",
            "LEFTMOUSE",
            ctrl=True,
            alt=True,
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

        addon_preferences.use_zbrush_style_rotate = True
        navigation_state.refresh_zbrush_navigation()
        addon_sculpt_keymap = keyconfigs.addon.keymaps.get("Sculpt")
        assert input_preferences.use_rotate_around_active is False
        assert _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_ENABLE", "LEFT_ALT", "PRESS")
        assert _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_DISABLE", "LEFT_ALT", "RELEASE")
        assert not _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_ENABLE", "LEFT_SHIFT", "PRESS")
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.zbrush_rotate_modal", "RIGHTMOUSE", value="CLICK_DRAG")
        assert not _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.zbrush_rotate_modal", "RIGHTMOUSE")
        assert _has_keymap_item(addon_sculpt_keymap, "zbrush_navigation.zbrush_rotate_modal", "RIGHTMOUSE", shift=True)
        assert not _has_keymap_item(addon_sculpt_keymap, "view3d.rotate", "RIGHTMOUSE")

        navigation_state.restore_zbrush_navigation()
        assert input_preferences.use_mouse_emulate_3_button is True
        assert input_preferences.use_rotate_around_active is False
        assert _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_ENABLE", "LEFT_ALT", "PRESS")
        assert _has_modal_keymap_item(rotate_modal_keymap, "AXIS_SNAP_DISABLE", "LEFT_ALT", "RELEASE")
        assert not _has_runtime_navigation_items(addon_sculpt_keymap), "Runtime Sculpt keymap items were not removed"
        assert not _has_runtime_navigation_items(addon_view3d_keymap), "Runtime 3D View keymap items were not removed"
    finally:
        if navigation_state._runtime_state.applied:
            navigation_state.restore_zbrush_navigation()
        if "rotate_modal_keymap" in locals():
            _remove_rotate_modal_axis_snap_items(rotate_modal_keymap)
        addon_preferences.use_zbrush_style_rotate = False
        input_preferences.use_mouse_emulate_3_button = original_emulate_3_button
        input_preferences.use_rotate_around_active = original_rotate_around_active


def test_sculpt_mode_addon_disable_restores_navigation() -> None:
    import zbrush_navigation.functions.navigation_state as navigation_state

    keyconfigs = bpy.context.window_manager.keyconfigs
    input_preferences = bpy.context.preferences.inputs
    original_emulate_3_button = input_preferences.use_mouse_emulate_3_button
    original_rotate_around_active = input_preferences.use_rotate_around_active

    try:
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()
        bpy.ops.mesh.primitive_cube_add(size=2.0)
        bpy.ops.object.mode_set(mode="SCULPT")

        input_preferences.use_mouse_emulate_3_button = True
        input_preferences.use_rotate_around_active = False
        navigation_state.apply_zbrush_navigation()
        assert navigation_state._runtime_state.applied

        bpy.ops.preferences.addon_disable(module=ADDON_MODULE)

        addon_sculpt_keymap = keyconfigs.addon.keymaps.get("Sculpt")
        addon_view3d_keymap = keyconfigs.addon.keymaps.get("3D View")
        assert addon_sculpt_keymap is None or not _has_runtime_navigation_items(addon_sculpt_keymap)
        assert addon_view3d_keymap is None or not _has_runtime_navigation_items(addon_view3d_keymap)
        assert input_preferences.use_mouse_emulate_3_button is True
        assert input_preferences.use_rotate_around_active is False
    finally:
        if bpy.context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        input_preferences.use_mouse_emulate_3_button = original_emulate_3_button
        input_preferences.use_rotate_around_active = original_rotate_around_active
        if bpy.context.preferences.addons.get(ADDON_MODULE) is None:
            bpy.ops.preferences.addon_enable(module=ADDON_MODULE)


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


def test_multires_level_operators() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    obj = bpy.context.object
    bpy.ops.object.mode_set(mode="SCULPT")

    bpy.ops.zbrush_navigation.multires_level_up()
    modifier = obj.modifiers.get("Multires")
    assert modifier is not None, "Ctrl+D did not create a Multires modifier"
    assert modifier.total_levels == 1
    assert modifier.sculpt_levels == 1
    assert modifier.levels == 1
    assert obj.mode == "SCULPT"

    bpy.ops.zbrush_navigation.multires_level_up()
    assert modifier.total_levels == 2
    assert modifier.sculpt_levels == 2
    assert modifier.levels == 2

    bpy.ops.zbrush_navigation.multires_existing_level_up()
    assert modifier.total_levels == 3
    assert modifier.sculpt_levels == 3
    assert modifier.levels == 3

    bpy.ops.zbrush_navigation.multires_level_down()
    assert modifier.total_levels == 3
    assert modifier.sculpt_levels == 2
    assert modifier.levels == 2

    bpy.ops.object.mode_set(mode="OBJECT")


def test_empty_drag_voxel_remesh_helpers() -> None:
    from zbrush_navigation.operators.mask import _object_has_sculpt_mask, _run_empty_drag_voxel_remesh

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    obj = bpy.context.object
    assert not _object_has_sculpt_mask(obj)

    mask_attribute = obj.data.attributes.new(".sculpt_mask", "FLOAT", "POINT")
    assert not _object_has_sculpt_mask(obj)
    mask_attribute.data[0].value = 0.5
    assert _object_has_sculpt_mask(obj)

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    obj = bpy.context.object
    obj.data.remesh_voxel_size = 0.5
    modifier = obj.modifiers.new(name="Multires", type="MULTIRES")
    bpy.ops.object.multires_subdivide(modifier=modifier.name, mode="CATMULL_CLARK")

    _run_empty_drag_voxel_remesh(bpy.context)

    remeshed_vertex_count = len(obj.data.vertices)
    assert all(modifier.type != "MULTIRES" for modifier in obj.modifiers)
    assert remeshed_vertex_count > 8

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    obj = bpy.context.object
    obj.data.remesh_voxel_size = 0.5
    shared_mesh = obj.data
    linked_obj = obj.copy()
    linked_obj.data = shared_mesh
    bpy.context.collection.objects.link(linked_obj)
    assert shared_mesh.users == 2
    modifier = obj.modifiers.new(name="Multires", type="MULTIRES")
    bpy.ops.object.multires_subdivide(modifier=modifier.name, mode="CATMULL_CLARK")

    _run_empty_drag_voxel_remesh(bpy.context)

    assert obj.data is not shared_mesh
    assert obj.data.users == 1
    assert shared_mesh.users == 1
    assert all(modifier.type != "MULTIRES" for modifier in obj.modifiers)
    assert len(obj.data.vertices) > 8


def test_mask_drag_value_uses_release_alt_state() -> None:
    from types import SimpleNamespace

    from zbrush_navigation.operators.mask import _drag_mask_value

    assert _drag_mask_value(SimpleNamespace(alt=False)) == 1.0
    assert _drag_mask_value(SimpleNamespace(alt=True)) == 0.0


def test_mask_selection_overlay_helpers() -> None:
    from types import SimpleNamespace

    from zbrush_navigation.operators.mask import (
        ADD_MASK_OVERLAY_FILL_COLOR,
        SUBTRACT_MASK_OVERLAY_FILL_COLOR,
        _mask_overlay_colors,
        _translate_lasso_path,
    )

    assert _mask_overlay_colors(SimpleNamespace(_is_subtracting=False))[0] == ADD_MASK_OVERLAY_FILL_COLOR
    assert _mask_overlay_colors(SimpleNamespace(_is_subtracting=True))[0] == SUBTRACT_MASK_OVERLAY_FILL_COLOR
    assert _translate_lasso_path([(1.0, 2.0, 0.0), (3.0, 4.0, 0.5)], 10.0, -1.0) == [
        (11.0, 1.0, 0.0),
        (13.0, 3.0, 0.5),
    ]



def test_faceset_helpers() -> None:
    from types import SimpleNamespace

    from zbrush_navigation.operators import faceset
    from zbrush_navigation.operators.faceset import (
        FACESET_ADD_OVERLAY_FILL_COLOR,
        FACESET_HIDE_OVERLAY_FILL_COLOR,
        _faceset_overlay_colors,
        _get_face_set_id,
        _to_operator_path,
    )

    assert _faceset_overlay_colors(SimpleNamespace(_is_hiding=False))[0] == FACESET_ADD_OVERLAY_FILL_COLOR
    assert _faceset_overlay_colors(SimpleNamespace(_is_hiding=True))[0] == FACESET_HIDE_OVERLAY_FILL_COLOR
    assert _to_operator_path([(1.0, 2.0, 0.0), (3.0, 4.0, 0.5)]) == [
        {"name": "0", "loc": (1.0, 2.0), "time": 0.0},
        {"name": "1", "loc": (3.0, 4.0), "time": 0.5},
    ]

    calls = []
    fake_bpy = SimpleNamespace(
        ops=SimpleNamespace(
            paint=SimpleNamespace(
                hide_show_all=lambda **kwargs: calls.append(("show_all", kwargs)),
                visibility_invert=lambda **kwargs: calls.append(("invert", kwargs)),
            ),
            sculpt=SimpleNamespace(face_set_change_visibility=lambda **kwargs: calls.append(("visibility", kwargs))),
        )
    )
    original_bpy = faceset.bpy
    try:
        faceset.bpy = fake_bpy
        mesh = SimpleNamespace(
            attributes={
                ".sculpt_face_set": SimpleNamespace(
                    domain="FACE",
                    data=[SimpleNamespace(value=7), SimpleNamespace(value=8), SimpleNamespace(value=8)],
                )
            }
        )
        obj = SimpleNamespace(data=mesh)

        faceset._apply_faceset_visibility_click(obj, 7, False)
        assert calls == [
            ("show_all", {"action": "SHOW"}),
            ("visibility", {"mode": "TOGGLE", "active_face_set": 7}),
        ]
        calls.clear()

        mesh.attributes[".hide_poly"] = SimpleNamespace(
            domain="FACE",
            data=[SimpleNamespace(value=False), SimpleNamespace(value=True), SimpleNamespace(value=True)],
        )
        faceset._apply_faceset_visibility_click(obj, 7, False)
        assert calls == [("invert", {})]
        calls.clear()

        mesh.attributes[".hide_poly"] = SimpleNamespace(
            domain="FACE",
            data=[SimpleNamespace(value=False), SimpleNamespace(value=False), SimpleNamespace(value=True)],
        )
        faceset._apply_faceset_visibility_click(obj, 7, False)
        assert calls == [("visibility", {"mode": "HIDE_ACTIVE", "active_face_set": 7})]
        calls.clear()

        faceset._apply_faceset_visibility_click(obj, 7, True)
        assert calls == [("visibility", {"mode": "HIDE_ACTIVE", "active_face_set": 7})]
        calls.clear()

        mesh.attributes.pop(".hide_poly")
        faceset._invert_visibility_if_any_hidden(obj)
        assert calls == []

        mesh.attributes[".hide_poly"] = SimpleNamespace(
            domain="FACE",
            data=[SimpleNamespace(value=False), SimpleNamespace(value=False), SimpleNamespace(value=False)],
        )
        faceset._invert_visibility_if_any_hidden(obj)
        assert calls == []

        mesh.attributes[".hide_poly"] = SimpleNamespace(
            domain="FACE",
            data=[SimpleNamespace(value=False), SimpleNamespace(value=True), SimpleNamespace(value=False)],
        )
        faceset._invert_visibility_if_any_hidden(obj)
        assert calls == [("invert", {})]
    finally:
        faceset.bpy = original_bpy

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    bpy.ops.mesh.primitive_cube_add(size=2.0)
    obj = bpy.context.object
    face_set_attribute = obj.data.attributes.new(".sculpt_face_set", "INT", "FACE")
    face_set_attribute.data[0].value = 7
    assert _get_face_set_id(obj, 0) == 7


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


def _get_addon_preferences():
    addon = bpy.context.preferences.addons.get(ADDON_MODULE)
    assert addon is not None, "Missing add-on preferences"
    return addon.preferences

def _get_or_create_user_rotate_modal_keymap(user_keyconfig):
    keymap = user_keyconfig.keymaps.get("View3D Rotate Modal")
    if keymap is not None:
        return keymap
    return user_keyconfig.keymaps.new(name="View3D Rotate Modal", modal=True)


def _remove_rotate_modal_axis_snap_items(keymap) -> None:
    for keymap_item in reversed(list(keymap.keymap_items)):
        if keymap_item.propvalue in {"AXIS_SNAP_ENABLE", "AXIS_SNAP_DISABLE"}:
            keymap.keymap_items.remove(keymap_item)


def _has_modal_keymap_item(keymap, propvalue: str, event_type: str, value: str) -> bool:
    for keymap_item in keymap.keymap_items:
        if keymap_item.propvalue == propvalue and keymap_item.type == event_type and keymap_item.value == value:
            return True
    return False

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
        "zbrush_navigation.snap_view_to_nearest_axis",
        "zbrush_navigation.mask_pen_input",
        "zbrush_navigation.mask_lasso_input",
        "zbrush_navigation.mask_filter_click",
        "zbrush_navigation.faceset_polygroup_input",
        "zbrush_navigation.multires_existing_level_up",
        "zbrush_navigation.multires_level_up",
        "zbrush_navigation.multires_level_down",
        "paint.mask_lasso_gesture",
        "sculpt.brush_stroke",
        "view3d.rotate",
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
