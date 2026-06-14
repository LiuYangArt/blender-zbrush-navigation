from __future__ import annotations

import bpy


class ZNAV_PG_settings(bpy.types.PropertyGroup):
    enable_zbrush_navigation: bpy.props.BoolProperty(
        name="Enable ZBrush Navigation",
        description="Enable this add-on's ZBrush-style navigation behavior",
        default=True,
    )
    orbit_mode: bpy.props.EnumProperty(
        name="Orbit Mode",
        description="Navigation orbit behavior to use for future navigation operators",
        items=(
            ("TURNTABLE", "Turntable", "Use Blender turntable-style orbit behavior"),
            ("TRACKBALL", "Trackball", "Use Blender trackball-style orbit behavior"),
        ),
        default="TURNTABLE",
    )


def register():
    bpy.types.WindowManager.zbrush_navigation_settings = bpy.props.PointerProperty(type=ZNAV_PG_settings)


def unregister():
    del bpy.types.WindowManager.zbrush_navigation_settings