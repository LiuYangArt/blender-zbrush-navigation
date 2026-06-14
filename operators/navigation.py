from __future__ import annotations

import bpy

from ..functions.navigation_state import format_settings_summary


class ZNAV_OT_report_status(bpy.types.Operator):
    """Report the current ZBrush Navigation state."""

    bl_idname = "zbrush_navigation.report_status"
    bl_label = "Report Navigation Status"
    bl_description = "Print the current ZBrush Navigation state"
    bl_options = {"REGISTER"}

    def execute(self, context):
        settings = context.window_manager.zbrush_navigation_settings
        message = format_settings_summary(settings)
        print(message)
        self.report({"INFO"}, message)
        return {"FINISHED"}