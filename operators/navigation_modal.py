from __future__ import annotations

from math import hypot

import bpy
from mathutils import Quaternion, Vector

from ..functions.view_snap import (
    AxisView,
    get_next_axis_view_from_drag,
    snap_region_3d_to_axis,
    snap_region_3d_to_nearest_axis,
)
from .view_snap import _get_drag_snap_threshold_pixels


ROTATE_SENSITIVITY = 0.006


class ZNAV_OT_zbrush_rotate_modal(bpy.types.Operator):
    bl_idname = "zbrush_navigation.zbrush_rotate_modal"
    bl_label = "ZBrush Rotate Modal"
    bl_description = "Use RMB drag to rotate, and Shift during rotate to snap to axis views"
    bl_options = {"REGISTER", "UNDO"}

    _region_3d = None
    _orbit_center = None
    _orbit_center_view_offset = None
    _axis_view: AxisView | None = None
    _last_mouse_x = 0
    _last_mouse_y = 0
    _drag_snap_threshold_pixels = 0.0
    _snap_active = False

    @classmethod
    def poll(cls, context):
        space_data = getattr(context, "space_data", None)
        return bool(space_data and getattr(space_data, "type", None) == "VIEW_3D" and space_data.region_3d)

    def invoke(self, context, event):
        self._region_3d = context.space_data.region_3d
        self._orbit_center = _get_active_object_center(context)
        self._orbit_center_view_offset = _get_view_offset(self._region_3d, self._orbit_center)
        self._last_mouse_x = event.mouse_region_x
        self._last_mouse_y = event.mouse_region_y
        self._drag_snap_threshold_pixels = _get_drag_snap_threshold_pixels(context)
        if event.shift:
            self._begin_snap(event)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "RIGHTMOUSE" and event.value == "RELEASE":
            return {"FINISHED"}
        if event.type in {"ESC", "LEFTMOUSE"}:
            return {"CANCELLED"}
        if event.type == "MOUSEMOVE":
            self._handle_mouse_move(event)
        return {"RUNNING_MODAL"}

    def _handle_mouse_move(self, event) -> None:
        if event.shift:
            if not self._snap_active:
                self._begin_snap(event)
            self._snap_next_axis_if_drag_passed_threshold(event)
            return

        self._snap_active = False
        delta_x = event.mouse_region_x - self._last_mouse_x
        delta_y = event.mouse_region_y - self._last_mouse_y
        if delta_x != 0 or delta_y != 0:
            self._rotate_view(delta_x, delta_y)
        self._last_mouse_x = event.mouse_region_x
        self._last_mouse_y = event.mouse_region_y

    def _begin_snap(self, event) -> None:
        self._axis_view = snap_region_3d_to_nearest_axis(self._region_3d)
        _preserve_orbit_center_screen_offset(self._region_3d, self._orbit_center, self._orbit_center_view_offset)
        self._last_mouse_x = event.mouse_region_x
        self._last_mouse_y = event.mouse_region_y
        self._snap_active = True

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
        _preserve_orbit_center_screen_offset(self._region_3d, self._orbit_center, self._orbit_center_view_offset)
        self._last_mouse_x = event.mouse_region_x
        self._last_mouse_y = event.mouse_region_y

    def _rotate_view(self, delta_x: float, delta_y: float) -> None:
        view_rotation = self._region_3d.view_rotation.copy()
        screen_right = view_rotation @ Vector((1.0, 0.0, 0.0))
        yaw = Quaternion(Vector((0.0, 0.0, 1.0)), -delta_x * ROTATE_SENSITIVITY)
        pitch = Quaternion(screen_right, delta_y * ROTATE_SENSITIVITY)
        new_rotation = yaw @ pitch @ view_rotation
        _set_view_rotation_around_center(
            self._region_3d,
            self._orbit_center,
            self._orbit_center_view_offset,
            new_rotation,
        )


def _get_view_offset(region_3d, center: Vector) -> Vector:
    return region_3d.view_rotation.inverted() @ (center - region_3d.view_location)


def _preserve_orbit_center_screen_offset(region_3d, center: Vector, center_view_offset: Vector) -> None:
    region_3d.view_location = center - (region_3d.view_rotation @ center_view_offset)


def _set_view_rotation_around_center(region_3d, center: Vector, center_view_offset: Vector, view_rotation: Quaternion) -> None:
    region_3d.view_rotation = view_rotation
    _preserve_orbit_center_screen_offset(region_3d, center, center_view_offset)


def _get_active_object_center(context) -> Vector:
    active_object = context.active_object
    if active_object is None:
        raise RuntimeError("Cannot rotate around active object center because no active object is available")
    if not active_object.bound_box:
        raise RuntimeError(f"Cannot rotate around active object center because {active_object.name} has no bound box")

    center = Vector((0.0, 0.0, 0.0))
    for corner in active_object.bound_box:
        center += active_object.matrix_world @ Vector(corner)
    return center / len(active_object.bound_box)