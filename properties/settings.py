from __future__ import annotations

import bpy


def _refresh_runtime_navigation_keymaps(self, context) -> None:
    from ..functions.navigation_state import refresh_zbrush_navigation

    refresh_zbrush_navigation()


class ZNAV_PG_settings(bpy.types.PropertyGroup):
    enable_zbrush_navigation: bpy.props.BoolProperty(
        name="Enable ZBrush Navigation",
        description="Use ZBrush-style View3D navigation only while Sculpt Mode is active",
        default=True,
    )
    mask_input_mode: bpy.props.EnumProperty(
        name="Mask Input",
        description="Choose the ZBrush-style mask input gesture",
        items=(
            ("PEN", "Pen", "Use brush-based mask input"),
            ("LASSO", "Lasso", "Use lasso-based mask input"),
        ),
        default="PEN",
        update=_refresh_runtime_navigation_keymaps,
    )
    pen_outside_drag_mode: bpy.props.EnumProperty(
        name="Pen Outside Drag",
        description="Gesture used when Pen mask starts outside the sculpt object",
        items=(
            ("LASSO", "Lasso", "Use native lasso mask gesture"),
            ("BOX", "Box", "Use native box mask gesture"),
        ),
        default="LASSO",
    )


def register():
    bpy.types.WindowManager.zbrush_navigation_settings = bpy.props.PointerProperty(type=ZNAV_PG_settings)


def unregister():
    del bpy.types.WindowManager.zbrush_navigation_settings