from __future__ import annotations

import bpy

from ..functions.reproject import DetailProjectionInputError, project_details_from_selected_high_mesh


class ZNAV_OT_project_details_from_selected_high_mesh(bpy.types.Operator):
    bl_idname = "zbrush_navigation.project_details_from_selected_high_mesh"
    bl_label = "Project Details From Selected High Mesh"
    bl_description = "Project selected high mesh surface detail onto the active target current Multires sculpt level"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return obj is not None and obj.type == "MESH"

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        try:
            result = project_details_from_selected_high_mesh(context)
        except DetailProjectionInputError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        except Exception as error:
            raise RuntimeError("Failed to project details from selected high mesh") from error

        self.report(
            {"INFO"},
            f"Projected {result.moved_vertex_count}/{result.vertex_count} vertices to {result.target_name} "
            f"Multires level {result.level} from {len(result.source_names)} source(s)",
        )
        return {"FINISHED"}