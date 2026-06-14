from __future__ import annotations

import bpy
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d


class ZNAV_OT_mask_ctrl_click(bpy.types.Operator):
    bl_idname = "zbrush_navigation.mask_ctrl_click"
    bl_label = "ZBrush Mask Ctrl Click"
    bl_description = "Invert sculpt mask when Ctrl+LMB clicks outside the active sculpt object"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _can_use_sculpt_mask(context)

    def invoke(self, context, event):
        if _event_hits_active_object(context, event):
            return {"PASS_THROUGH"}
        bpy.ops.paint.mask_flood_fill(mode="INVERT")
        return {"FINISHED"}


class ZNAV_OT_mask_pen_input(bpy.types.Operator):
    bl_idname = "zbrush_navigation.mask_pen_input"
    bl_label = "ZBrush Mask Pen Input"
    bl_description = "Use brush mask on-object and native box mask when dragging from outside the sculpt object"
    bl_options = {"REGISTER", "UNDO"}

    value: bpy.props.FloatProperty(default=1.0)

    @classmethod
    def poll(cls, context):
        return _can_use_sculpt_mask(context)

    def invoke(self, context, event):
        if _event_hits_active_object(context, event):
            return {"PASS_THROUGH"}
        return bpy.ops.paint.mask_box_gesture("INVOKE_DEFAULT", mode="VALUE", value=self.value)


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
