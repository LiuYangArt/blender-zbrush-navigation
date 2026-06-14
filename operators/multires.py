from __future__ import annotations

from contextlib import contextmanager

import bpy


class ZNAV_OT_multires_level_up(bpy.types.Operator):
    bl_idname = "zbrush_navigation.multires_level_up"
    bl_label = "ZBrush Multires Level Up"
    bl_description = "Increase the active sculpt object's Multires level, adding one if already at the highest level"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _can_use_multires(context)

    def execute(self, context):
        obj = context.object
        try:
            modifier = _get_or_create_multires_modifier(obj)
            target_level, total_levels = _increase_multires_level(obj, modifier)
        except Exception as error:
            raise RuntimeError(f"Failed to increase Multires level for {obj.name}") from error

        self.report({"INFO"}, f"Multires level {target_level}/{total_levels}")
        return {"FINISHED"}


class ZNAV_OT_multires_existing_level_up(bpy.types.Operator):
    bl_idname = "zbrush_navigation.multires_existing_level_up"
    bl_label = "ZBrush Existing Multires Level Up"
    bl_description = "Increase Multires level only when the active sculpt object already has Multires"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _can_use_multires(context)

    def invoke(self, context, event):
        if _find_multires_modifier(context.object) is None:
            return {"PASS_THROUGH"}
        return self.execute(context)

    def execute(self, context):
        obj = context.object
        modifier = _find_multires_modifier(obj)
        if modifier is None:
            return {"PASS_THROUGH"}

        try:
            target_level, total_levels = _increase_multires_level(obj, modifier)
        except Exception as error:
            raise RuntimeError(f"Failed to increase existing Multires level for {obj.name}") from error

        self.report({"INFO"}, f"Multires level {target_level}/{total_levels}")
        return {"FINISHED"}


class ZNAV_OT_multires_level_down(bpy.types.Operator):
    bl_idname = "zbrush_navigation.multires_level_down"
    bl_label = "ZBrush Multires Level Down"
    bl_description = "Lower the active sculpt object's current Multires display level"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return _can_use_multires(context)

    def execute(self, context):
        obj = context.object
        modifier = _find_multires_modifier(obj)
        if modifier is None:
            self.report({"WARNING"}, "Active sculpt object has no Multires modifier")
            return {"CANCELLED"}

        try:
            target_level = max(0, _get_current_multires_level(modifier) - 1)
            _set_current_multires_level(modifier, target_level)
        except Exception as error:
            raise RuntimeError(f"Failed to lower Multires level for {obj.name}") from error

        self.report({"INFO"}, f"Multires level {target_level}/{modifier.total_levels}")
        return {"FINISHED"}


def _can_use_multires(context) -> bool:
    obj = context.object
    return bool(context.mode == "SCULPT" and obj is not None and obj.type == "MESH")


@contextmanager
def _temporary_object_mode(obj):
    original_mode = obj.mode
    if original_mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    try:
        yield
    finally:
        if obj.mode != original_mode:
            bpy.ops.object.mode_set(mode=original_mode)


def _get_or_create_multires_modifier(obj) -> bpy.types.MultiresModifier:
    modifier = _find_multires_modifier(obj)
    if modifier is not None:
        return modifier
    return obj.modifiers.new(name="Multires", type="MULTIRES")


def _find_multires_modifier(obj) -> bpy.types.MultiresModifier | None:
    active_modifier = getattr(obj.modifiers, "active", None)
    if active_modifier is not None and active_modifier.type == "MULTIRES":
        return active_modifier
    for modifier in obj.modifiers:
        if modifier.type == "MULTIRES":
            return modifier
    return None


def _increase_multires_level(obj, modifier: bpy.types.MultiresModifier) -> tuple[int, int]:
    with _temporary_object_mode(obj):
        current_level = _get_current_multires_level(modifier)
        total_levels = modifier.total_levels
        if current_level >= total_levels:
            _subdivide_multires(modifier)
            total_levels = modifier.total_levels
        target_level = min(current_level + 1, total_levels)
        _set_current_multires_level(modifier, target_level)
    return target_level, total_levels


def _subdivide_multires(modifier: bpy.types.MultiresModifier) -> None:
    bpy.ops.object.multires_subdivide(modifier=modifier.name, mode="CATMULL_CLARK")


def _get_current_multires_level(modifier: bpy.types.MultiresModifier) -> int:
    return modifier.sculpt_levels


def _set_current_multires_level(modifier: bpy.types.MultiresModifier, level: int) -> None:
    level = min(level, modifier.total_levels)
    modifier.levels = level
    modifier.sculpt_levels = level