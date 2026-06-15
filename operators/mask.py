from __future__ import annotations

from math import hypot, sqrt
from time import perf_counter

import bpy
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d


MASK_DRAG_THRESHOLD_PIXELS = 4.0
LASSO_MIN_POINT_DISTANCE_PIXELS = 1.5
LASSO_HIT_TEST_TARGET_SAMPLES = 2500
LASSO_HIT_TEST_MIN_STEP_PIXELS = 8.0


class ZNAV_OT_mask_pen_input(bpy.types.Operator):
    bl_idname = "zbrush_navigation.mask_pen_input"
    bl_label = "ZBrush Mask Pen Input"
    bl_description = "Change the mask on outside Ctrl+click, or start the configured mask gesture on outside Ctrl+drag"
    bl_options = {"REGISTER", "UNDO"}

    value: bpy.props.FloatProperty(default=1.0)

    _start_mouse_x = 0
    _start_mouse_y = 0
    _drag_started = False

    @classmethod
    def poll(cls, context):
        return _can_use_sculpt_mask(context)

    def invoke(self, context, event):
        if _event_hits_active_object(context, event):
            return {"PASS_THROUGH"}

        self._start_mouse_x = event.mouse_region_x
        self._start_mouse_y = event.mouse_region_y
        self._drag_started = False
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE" and not self._drag_started and self._drag_distance(event) >= MASK_DRAG_THRESHOLD_PIXELS:
            self._drag_started = True
            settings = context.window_manager.zbrush_navigation_settings
            result = _invoke_pen_outside_drag_gesture(settings.pen_outside_drag_mode, self.value)
            if "CANCELLED" in result:
                return {"CANCELLED"}
            return {"FINISHED"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if self._drag_started:
                return {"FINISHED"}
            if self.value == 1.0:
                bpy.ops.paint.mask_flood_fill(mode="INVERT")
                return {"FINISHED"}
            if self.value == 0.0:
                bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0.0)
                return {"FINISHED"}
            raise RuntimeError(f"Unsupported mask click value: {self.value}")

        return {"RUNNING_MODAL"}

    def _drag_distance(self, event) -> float:
        return hypot(event.mouse_region_x - self._start_mouse_x, event.mouse_region_y - self._start_mouse_y)


class ZNAV_OT_mask_lasso_input(bpy.types.Operator):
    bl_idname = "zbrush_navigation.mask_lasso_input"
    bl_label = "ZBrush Mask Lasso Input"
    bl_description = "Draw a custom lasso, clear on empty selection, or apply native mask lasso on hit"
    bl_options = {"REGISTER", "UNDO"}

    value: bpy.props.FloatProperty(default=1.0)

    _area = None
    _region = None
    _region_3d = None
    _draw_handler = None
    _path = None
    _start_time = 0.0
    _start_hits_active_object = False
    _drag_started = False

    @classmethod
    def poll(cls, context):
        return _can_use_sculpt_mask(context)

    def invoke(self, context, event):
        self._area = context.area
        self._region = context.region
        self._region_3d = context.space_data.region_3d
        self._path = []
        self._start_time = perf_counter()
        self._start_hits_active_object = _event_hits_active_object(context, event)
        self._drag_started = False
        self._append_path_point(event)
        self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(_draw_lasso_overlay, (self,), "WINDOW", "POST_PIXEL")
        context.window_manager.modal_handler_add(self)
        self._tag_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._cleanup()
            return {"CANCELLED"}

        if event.type == "MOUSEMOVE":
            if self._append_path_point(event):
                self._drag_started = True
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            self._append_path_point(event, force=True)
            return self._finish_lasso(context)

        return {"RUNNING_MODAL"}

    def _append_path_point(self, event, *, force: bool = False) -> bool:
        point = (float(event.mouse_region_x), float(event.mouse_region_y), perf_counter() - self._start_time)
        if self._path and not force:
            last_x, last_y, _last_time = self._path[-1]
            if hypot(point[0] - last_x, point[1] - last_y) < LASSO_MIN_POINT_DISTANCE_PIXELS:
                return False
        self._path.append(point)
        return True

    def _finish_lasso(self, context):
        path = list(self._path)
        self._cleanup()

        if not self._drag_started or len(path) < 3:
            return self._handle_click(context)

        if _lasso_hits_active_object(context, self._region, self._region_3d, path):
            _apply_native_lasso_mask(path, self.value)
            return {"FINISHED"}

        if self.value == 1.0:
            bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0.0)
        return {"FINISHED"}

    def _handle_click(self, context):
        if self._start_hits_active_object:
            return {"CANCELLED"}
        if self.value == 1.0:
            bpy.ops.paint.mask_flood_fill(mode="INVERT")
            return {"FINISHED"}
        if self.value == 0.0:
            bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0.0)
            return {"FINISHED"}
        raise RuntimeError(f"Unsupported lasso click value: {self.value}")

    def _cleanup(self) -> None:
        if self._draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, "WINDOW")
            self._draw_handler = None
        self._tag_redraw()

    def _tag_redraw(self) -> None:
        if self._area is not None:
            self._area.tag_redraw()


def _draw_lasso_overlay(operator: ZNAV_OT_mask_lasso_input) -> None:
    if not operator._path or len(operator._path) < 2:
        return

    import gpu
    from gpu_extras.batch import batch_for_shader
    from mathutils import Vector
    from mathutils.geometry import tessellate_polygon

    coords = [(point[0], point[1]) for point in operator._path]
    closed_coords = coords + [coords[0]]
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    gpu.state.blend_set("ALPHA")
    if len(coords) >= 3:
        polygon = [[Vector((x, y, 0.0)) for x, y in coords]]
        indices = tessellate_polygon(polygon)
        fill_batch = batch_for_shader(shader, "TRIS", {"pos": coords}, indices=indices)
        shader.bind()
        shader.uniform_float("color", (0.0, 0.0, 0.0, 0.65))
        fill_batch.draw(shader)

    outline_batch = batch_for_shader(shader, "LINE_STRIP", {"pos": closed_coords})
    gpu.state.line_width_set(1.0)
    shader.bind()
    shader.uniform_float("color", (0.0, 0.0, 0.0, 0.62))
    outline_batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


def _invoke_pen_outside_drag_gesture(mode: str, value: float) -> set[str]:
    if mode == "BOX":
        return bpy.ops.paint.mask_box_gesture("INVOKE_DEFAULT", mode="VALUE", value=value)
    if mode == "LASSO":
        return bpy.ops.paint.mask_lasso_gesture("INVOKE_DEFAULT", mode="VALUE", value=value)
    raise RuntimeError(f"Unsupported Pen Outside Drag mode: {mode}")


def _apply_native_lasso_mask(path: list[tuple[float, float, float]], value: float) -> None:
    operator_path = [
        {"name": str(index), "loc": (point[0], point[1]), "time": point[2]}
        for index, point in enumerate(path)
    ]
    bpy.ops.paint.mask_lasso_gesture(path=operator_path, mode="VALUE", value=value)


def _lasso_hits_active_object(context, region, region_3d, path: list[tuple[float, float, float]]) -> bool:
    polygon = [(point[0], point[1]) for point in path]
    min_x, max_x, min_y, max_y = _polygon_bounds(polygon)
    width = max_x - min_x
    height = max_y - min_y
    if width <= 0.0 or height <= 0.0:
        return False

    step = max(LASSO_HIT_TEST_MIN_STEP_PIXELS, sqrt((width * height) / LASSO_HIT_TEST_TARGET_SAMPLES))
    y = min_y + step * 0.5
    while y <= max_y:
        x = min_x + step * 0.5
        while x <= max_x:
            if _point_in_polygon((x, y), polygon) and _screen_point_hits_active_object(context, region, region_3d, (x, y)):
                return True
            x += step
        y += step
    return False


def _polygon_bounds(polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return min(xs), max(xs), min(ys), max(ys)


def _point_in_polygon(point: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point
    inside = False
    previous_x, previous_y = polygon[-1]
    for current_x, current_y in polygon:
        crosses_y = (current_y > y) != (previous_y > y)
        if crosses_y:
            intersection_x = (previous_x - current_x) * (y - current_y) / (previous_y - current_y) + current_x
            if x < intersection_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _screen_point_hits_active_object(context, region, region_3d, mouse: tuple[float, float]) -> bool:
    origin = region_2d_to_origin_3d(region, region_3d, mouse)
    direction = region_2d_to_vector_3d(region, region_3d, mouse)
    depsgraph = context.evaluated_depsgraph_get()
    hit, _location, _normal, _index, hit_object, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
    return bool(hit and hit_object == context.active_object)


def _can_use_sculpt_mask(context) -> bool:
    space_data = getattr(context, "space_data", None)
    return bool(
        context.mode == "SCULPT"
        and context.active_object is not None
        and getattr(space_data, "type", None) == "VIEW_3D"
        and getattr(space_data, "region_3d", None) is not None
    )


def _event_hits_active_object(context, event) -> bool:
    region = context.region
    region_3d = context.space_data.region_3d
    mouse = (event.mouse_region_x, event.mouse_region_y)
    return _screen_point_hits_active_object(context, region, region_3d, mouse)
