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

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.zbrush_navigation_settings
        layout.prop(self, "show_sidebar_panel")
        layout.prop(settings, "enable_zbrush_navigation")
        layout.operator("zbrush_navigation.report_status", icon="INFO")
        layout.label(text=format_settings_summary(settings))