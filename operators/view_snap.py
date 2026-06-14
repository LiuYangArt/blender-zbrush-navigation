from __future__ import annotations

from math import hypot

import bpy

from ..functions.view_snap import (
    get_next_axis_view_from_drag,
    snap_region_3d_to_axis,
    snap_region_3d_to_nearest_axis,
)


class ZNAV_OT_snap_view_to_nearest_axis(bpy.types.Operator):
    bl_idname = "zbrush_navigation.snap_view_to_nearest_axis"
    bl_label = "Snap View to Nearest Axis"
    bl_description = "Snap the current 3D view to the nearest axis without changing projection"
    bl_options = {"REGISTER", "UNDO"}

    _region_3d = None
    _axis_view = None
    _last_mouse_x = 0
    _last_mouse_y = 0
    _drag_snap_threshold_pixels = 0.0

    @classmethod
    def poll(cls, context):
        space_data = getattr(context, "space_data", None)
        return bool(space_data and getattr(space_data, "type", None) == "VIEW_3D" and space_data.region_3d)

    def invoke(self, context, event):
        self._region_3d = context.space_data.region_3d
        self._axis_view = snap_region_3d_to_nearest_axis(self._region_3d)
        self._last_mouse_x = event.mouse_region_x
        self._last_mouse_y = event.mouse_region_y
        self._drag_snap_threshold_pixels = _get_drag_snap_threshold_pixels(context)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
            return {"FINISHED"}
        if event.type in {"ESC", "LEFTMOUSE"}:
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            if not event.shift:
                return {"FINISHED"}
            self._snap_next_axis_if_drag_passed_threshold(event)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        axis_view = snap_region_3d_to_nearest_axis(context.space_data.region_3d)
        self.report({"INFO"}, f"Snapped view to {axis_view.name.title()}")
        return {"FINISHED"}

    def _snap_next_axis_if_drag_passed_threshold(self, event) -> None:
        delta_x = event.mouse_region_x - self._last_mouse_x
        delta_y = event.mouse_region_y - self._last_mouse_y
        drag_distance = hypot(delta_x, delta_y)
        if drag_distance < self._drag_snap_threshold_pixels:
            return

        step_count = int(drag_distance // self._drag_snap_threshold_pixels)
        for _index in range(step_count):
            self._axis_view = get_next_axis_view_from_drag(self._axis_view, delta_x, delta_y)
        snap_region_3d_to_axis(self._region_3d, self._axis_view)
        self._last_mouse_x = event.mouse_region_x
        self._last_mouse_y = event.mouse_region_y


def _get_drag_snap_threshold_pixels(context) -> float:
    region = context.region
    if region is None or region.width <= 0 or region.height <= 0:
        raise RuntimeError("Cannot calculate snap drag distance without a valid View3D region")

    addon_id = __package__.rsplit(".", 1)[0]
    addon = context.preferences.addons.get(addon_id)
    if addon is None:
        raise RuntimeError(f"Cannot find add-on preferences for {addon_id}")

    percent = addon.preferences.snap_drag_threshold_percent / 100.0
    return min(region.width, region.height) * percent