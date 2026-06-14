from __future__ import annotations

import bpy


class ZNAV_PT_view3d_panel(bpy.types.Panel):
    bl_idname = "ZNAV_PT_view3d_panel"
    bl_label = "ZBrush Nav"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ZBrush Nav"

    @classmethod
    def poll(cls, context):
        addon_id = __package__.rsplit(".", 1)[0]
        addon = context.preferences.addons.get(addon_id)
        if addon is None:
            return True
        return addon.preferences.show_sidebar_panel

    def draw(self, context):
        layout = self.layout
        settings = context.window_manager.zbrush_navigation_settings
        layout.prop(settings, "enable_zbrush_navigation")
        layout.operator("zbrush_navigation.report_status", icon="INFO")