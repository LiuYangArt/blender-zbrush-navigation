from __future__ import annotations

import bpy

from ..functions.navigation_state import format_settings_summary


class ZNAV_AP_preferences(bpy.types.AddonPreferences):
    bl_idname = __package__.rsplit(".", 1)[0]

    show_sidebar_panel: bpy.props.BoolProperty(
        name="Show Sidebar Panel",
        description="Show the ZBrush Navigation panel in the View3D sidebar",
        default=True,
    )
    snap_drag_threshold_percent: bpy.props.FloatProperty(
        name="Snap Drag Distance (%)",
        description="Viewport size percentage to drag before stepping to the next snapped view",
        default=12.0,
        min=2.0,
        max=35.0,
        precision=1,
    )

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.zbrush_navigation_settings
        layout.prop(self, "show_sidebar_panel")
        layout.prop(self, "snap_drag_threshold_percent")
        layout.prop(settings, "enable_zbrush_navigation")
        layout.operator("zbrush_navigation.report_status", icon="INFO")
        layout.label(text=format_settings_summary(settings))