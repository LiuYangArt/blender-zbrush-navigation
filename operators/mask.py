from __future__ import annotations

from math import hypot

import bpy
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d


MASK_DRAG_THRESHOLD_PIXELS = 4.0


class ZNAV_OT_mask_pen_input(bpy.types.Operator):
    bl_idname = "zbrush_navigation.mask_pen_input"
    bl_label = "ZBrush Mask Pen Input"
    bl_description = "Change the mask on outside Ctrl+click, or start the configured mask gesture on outside Ctrl+drag"
    bl_options = {"REGISTER", "UNDO"}

    value: bpy.props.FloatProperty(default=1.0)

    _start_mouse_x = 0
    _start_mouse_y = 0
    _drag_started = False

    @classmethod
    def poll(cls, context):
        return _can_use_sculpt_mask(context)

    def invoke(self, context, event):
        if _event_hits_active_object(context, event):
            return {"PASS_THROUGH"}

        self._start_mouse_x = event.mouse_region_x
        self._start_mouse_y = event.mouse_region_y
        self._drag_started = False
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE" and not self._drag_started and self._drag_distance(event) >= MASK_DRAG_THRESHOLD_PIXELS:
            self._drag_started = True
            settings = context.window_manager.zbrush_navigation_settings
            result = _invoke_pen_outside_drag_gesture(settings.pen_outside_drag_mode, self.value)
            if "CANCELLED" in result:
                return {"CANCELLED"}
            return {"FINISHED"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if self._drag_started:
                return {"FINISHED"}
            if self.value == 1.0:
                bpy.ops.paint.mask_flood_fill(mode="INVERT")
                return {"FINISHED"}
            if self.value == 0.0:
                bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0.0)
                return {"FINISHED"}
            raise RuntimeError(f"Unsupported mask click value: {self.value}")

        return {"RUNNING_MODAL"}

    def _drag_distance(self, event) -> float:
        return hypot(event.mouse_region_x - self._start_mouse_x, event.mouse_region_y - self._start_mouse_y)


def _invoke_pen_outside_drag_gesture(mode: str, value: float) -> set[str]:
    if mode == "BOX":
        return bpy.ops.paint.mask_box_gesture("INVOKE_DEFAULT", mode="VALUE", value=value)
    if mode == "LASSO":
        return bpy.ops.paint.mask_lasso_gesture("INVOKE_DEFAULT", mode="VALUE", value=value)
    raise RuntimeError(f"Unsupported Pen Outside Drag mode: {mode}")


def _can_use_sculpt_mask(context) -> bool:
    space_data = getattr(context, "space_data", None)
    return bool(
        context.mode == "SCULPT"
        and context.active_object is not None
        and getattr(space_data, "type", None) == "VIEW_3D"
        and getattr(space_data, "region_3d", None) is not None
    )


def _event_hits_active_object(context, event) -> bool:
    region = context.region
    region_3d = context.space_data.region_3d
    mouse = (event.mouse_region_x, event.mouse_region_y)
    origin = region_2d_to_origin_3d(region, region_3d, mouse)
    direction = region_2d_to_vector_3d(region, region_3d, mouse)
    depsgraph = context.evaluated_depsgraph_get()
    hit, _location, _normal, _index, hit_object, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
    return bool(hit and hit_object == context.active_object)
