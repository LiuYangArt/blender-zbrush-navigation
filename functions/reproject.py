from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import bpy


@dataclass(frozen=True)
class DetailProjectionResult:
    target_name: str
    source_names: tuple[str, ...]
    modifier_name: str
    level: int
    vertex_count: int
    moved_vertex_count: int


class DetailProjectionInputError(ValueError):
    pass


def project_details_from_selected_high_mesh(context) -> DetailProjectionResult:
    target, modifier, sources = validate_project_detail_inputs(context)
    original_levels = modifier.levels
    original_sculpt_levels = modifier.sculpt_levels
    level = modifier.sculpt_levels
    vertex_count = 0
    moved_vertex_count = 0

    temp_objects: list[bpy.types.Object] = []
    temp_meshes: list[bpy.types.Mesh] = []

    with _preserve_object_context(context):
        try:
            _ensure_object_mode(target)
            modifier.levels = level
            modifier.sculpt_levels = level
            depsgraph = context.evaluated_depsgraph_get()

            reshape_object = _create_current_multires_object(target, depsgraph)
            temp_objects.append(reshape_object)
            temp_meshes.append(reshape_object.data)

            source_object = _create_combined_source_object(sources, depsgraph)
            temp_objects.append(source_object)
            temp_meshes.append(source_object.data)

            vertex_count = len(reshape_object.data.vertices)
            before_positions = [vertex.co.copy() for vertex in reshape_object.data.vertices]
            _shrinkwrap_object_to_source(reshape_object, source_object)
            moved_vertex_count = _count_moved_vertices(before_positions, reshape_object.data.vertices)
            _reshape_multires_from_object(target, modifier, reshape_object)
        except DetailProjectionInputError:
            raise
        except Exception as error:
            source_names = ", ".join(source.name for source in sources)
            raise RuntimeError(
                "Failed to project details: "
                f"target={target.name}, sources={source_names}, modifier={modifier.name}, level={level}"
            ) from error
        finally:
            modifier.levels = original_levels
            modifier.sculpt_levels = original_sculpt_levels
            _remove_temporary_data(temp_objects, temp_meshes)

    return DetailProjectionResult(
        target_name=target.name,
        source_names=tuple(source.name for source in sources),
        modifier_name=modifier.name,
        level=level,
        vertex_count=vertex_count,
        moved_vertex_count=moved_vertex_count,
    )


def validate_project_detail_inputs(context) -> tuple[bpy.types.Object, bpy.types.MultiresModifier, list[bpy.types.Object]]:
    target = context.view_layer.objects.active
    if target is None:
        raise DetailProjectionInputError("No active target object")
    if target.type != "MESH":
        raise DetailProjectionInputError(f"Active target {target.name} is not a mesh")
    if target.mode not in {"OBJECT", "SCULPT"}:
        raise DetailProjectionInputError(f"Target {target.name} must be in Object or Sculpt mode")
    if not target.is_editable or not target.data.is_editable:
        raise DetailProjectionInputError(f"Target {target.name} is not editable")

    modifier = find_multires_modifier(target)
    if modifier is None:
        raise DetailProjectionInputError(f"Target {target.name} has no Multires modifier")
    if modifier.sculpt_levels <= 0:
        raise DetailProjectionInputError(f"Target {target.name} Multires sculpt level is 0")
    if modifier.sculpt_levels > modifier.total_levels:
        raise DetailProjectionInputError(
            f"Target {target.name} Multires sculpt level {modifier.sculpt_levels} exceeds total levels {modifier.total_levels}"
        )

    sources = [obj for obj in context.selected_objects if obj != target and obj.type == "MESH"]
    if not sources:
        raise DetailProjectionInputError("Select at least one non-active mesh source")
    return target, modifier, sources


def find_multires_modifier(obj: bpy.types.Object) -> bpy.types.MultiresModifier | None:
    active_modifier = getattr(obj.modifiers, "active", None)
    if active_modifier is not None and active_modifier.type == "MULTIRES":
        return active_modifier
    for modifier in obj.modifiers:
        if modifier.type == "MULTIRES":
            return modifier
    return None


@contextmanager
def _preserve_object_context(context):
    view_layer = context.view_layer
    original_active = view_layer.objects.active
    original_selected = list(context.selected_objects)
    original_mode = original_active.mode if original_active is not None else "OBJECT"
    try:
        yield
    finally:
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")
        for obj in original_selected:
            if obj.name in bpy.data.objects:
                obj.select_set(True)
        if original_active is not None and original_active.name in bpy.data.objects:
            view_layer.objects.active = original_active
            if original_mode != "OBJECT":
                bpy.ops.object.mode_set(mode=original_mode)


def _ensure_object_mode(target: bpy.types.Object) -> None:
    bpy.context.view_layer.objects.active = target
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def _create_current_multires_object(target: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> bpy.types.Object:
    evaluated = target.evaluated_get(depsgraph)
    mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
    if len(mesh.vertices) == 0:
        bpy.data.meshes.remove(mesh)
        raise DetailProjectionInputError(f"Target {target.name} current Multires layer has no vertices")
    obj = bpy.data.objects.new(f"{target.name}_znav_reproject_shape", mesh)
    obj.matrix_world = target.matrix_world.copy()
    bpy.context.collection.objects.link(obj)
    return obj


def _create_combined_source_object(sources: list[bpy.types.Object], depsgraph: bpy.types.Depsgraph) -> bpy.types.Object:
    vertices = []
    faces = []
    for source in sources:
        source_mesh = bpy.data.meshes.new_from_object(source.evaluated_get(depsgraph), depsgraph=depsgraph)
        try:
            if len(source_mesh.polygons) == 0:
                raise DetailProjectionInputError(f"Source {source.name} has no surface faces")
            vertex_offset = len(vertices)
            vertices.extend(source.matrix_world @ vertex.co for vertex in source_mesh.vertices)
            faces.extend(tuple(vertex_offset + index for index in polygon.vertices) for polygon in source_mesh.polygons)
        finally:
            bpy.data.meshes.remove(source_mesh)

    mesh = bpy.data.meshes.new("znav_reproject_combined_source")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new("znav_reproject_combined_source", mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def _shrinkwrap_object_to_source(obj: bpy.types.Object, source: bpy.types.Object) -> None:
    modifier = obj.modifiers.new(name="ZBrush Nav Detail Projection", type="SHRINKWRAP")
    modifier.wrap_method = "NEAREST_SURFACEPOINT"
    modifier.wrap_mode = "ON_SURFACE"
    modifier.target = source
    _select_only(obj)
    result = bpy.ops.object.modifier_apply(modifier=modifier.name)
    if "FINISHED" not in result:
        raise RuntimeError(f"Blender failed to apply Shrinkwrap projection modifier to {obj.name}: {result}")


def _reshape_multires_from_object(
    target: bpy.types.Object,
    modifier: bpy.types.MultiresModifier,
    reshape_object: bpy.types.Object,
) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    reshape_object.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    if not bpy.ops.object.multires_reshape.poll():
        raise DetailProjectionInputError("Blender API cannot write to the target Multires current layer")
    result = bpy.ops.object.multires_reshape(modifier=modifier.name)
    if "FINISHED" not in result:
        raise RuntimeError(f"Blender failed to reshape Multires modifier {modifier.name}: {result}")


def _select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _count_moved_vertices(before_positions, after_vertices) -> int:
    return sum(1 for before, after in zip(before_positions, after_vertices) if (after.co - before).length > 0.000001)


def _remove_temporary_data(objects: list[bpy.types.Object], meshes: list[bpy.types.Mesh]) -> None:
    for obj in reversed(objects):
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in reversed(meshes):
        if mesh.name in bpy.data.meshes and mesh.users == 0:
            bpy.data.meshes.remove(mesh)