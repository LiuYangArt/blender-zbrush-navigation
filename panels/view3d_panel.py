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
        layout.prop(settings, "mask_input_mode", expand=True)
        if settings.mask_input_mode == "PEN":
            layout.prop(settings, "pen_outside_drag_mode", expand=True)
        layout.prop(settings, "enable_empty_drag_voxel_remesh")
        layout.prop(settings, "mask_front_faces_only")
        layout.separator()
        layout.prop(settings, "faceset_gesture", expand=True)
        layout.prop(settings, "faceset_front_faces_only")
        if settings.faceset_gesture == "LINE":
            layout.prop(settings, "faceset_line_limit_to_segment")
        layout.separator()
        layout.operator("zbrush_navigation.project_details_from_selected_high_mesh", icon="MOD_MULTIRES")
        layout.operator("zbrush_navigation.report_status", icon="INFO")
