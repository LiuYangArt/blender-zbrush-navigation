from __future__ import annotations

import bpy


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
    )


def register():
    bpy.types.WindowManager.zbrush_navigation_settings = bpy.props.PointerProperty(type=ZNAV_PG_settings)


def unregister():
    del bpy.types.WindowManager.zbrush_navigation_settings