from __future__ import annotations

from math import hypot, sqrt
from time import perf_counter

import bpy
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d


DEFAULT_MASK_DRAG_THRESHOLD_PIXELS = 10.0
LASSO_MIN_POINT_DISTANCE_PIXELS = 1.5
LASSO_HIT_TEST_TARGET_SAMPLES = 2500
LASSO_HIT_TEST_MIN_STEP_PIXELS = 8.0
ADD_MASK_OVERLAY_FILL_COLOR = (0.0, 0.0, 0.0, 0.65)
ADD_MASK_OVERLAY_OUTLINE_COLOR = (1.0, 1.0, 1.0, 0.5)
SUBTRACT_MASK_OVERLAY_FILL_COLOR = (1.0, 1.0, 1.0, 0.15)
SUBTRACT_MASK_OVERLAY_OUTLINE_COLOR = (1.0, 1.0, 1.0, 0.5)
MASK_VALUE_EPSILON = 1e-6


class ZNAV_OT_mask_pen_input(bpy.types.Operator):
    bl_idname = "zbrush_navigation.mask_pen_input"
    bl_label = "ZBrush Mask Pen Input"
    bl_description = "Change the mask on outside Ctrl+click, or start the configured mask gesture on outside Ctrl+drag"
    bl_options = {"REGISTER", "UNDO"}

    value: bpy.props.FloatProperty(default=1.0)

    _area = None
    _region = None
    _region_3d = None
    _draw_handler = None
    _start_mouse_x = 0.0
    _start_mouse_y = 0.0
    _current_mouse_x = 0.0
    _current_mouse_y = 0.0
    _drag_started = False
    _is_subtracting = False
    _is_moving_selection = False
    _move_mouse_x = 0.0
    _move_mouse_y = 0.0
    _path = None
    _start_time = 0.0
    _outside_drag_mode = None

    @classmethod
    def poll(cls, context):
        return _can_use_sculpt_mask(context)

    def invoke(self, context, event):
        if _event_hits_active_object(context, event):
            return {"PASS_THROUGH"}

        self._area = context.area
        self._region = context.region
        self._region_3d = context.space_data.region_3d
        self._draw_handler = None
        self._start_mouse_x = float(event.mouse_region_x)
        self._start_mouse_y = float(event.mouse_region_y)
        self._current_mouse_x = self._start_mouse_x
        self._current_mouse_y = self._start_mouse_y
        self._path = []
        self._start_time = perf_counter()
        self._drag_started = False
        self._outside_drag_mode = None
        self._is_subtracting = _event_is_subtracting(event)
        self._is_moving_selection = False
        self._move_mouse_x = self._start_mouse_x
        self._move_mouse_y = self._start_mouse_y
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._cleanup()
            return {"CANCELLED"}

        self._update_subtract_mode(event)

        if event.type == "SPACE" and self._drag_started:
            self._handle_space_event(event)
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            self._handle_mouse_move(context, event)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if self._drag_started:
                return self._finish_outside_drag(context, event)
            return self._handle_click()

        return {"RUNNING_MODAL"}

    def _handle_mouse_move(self, context, event) -> None:
        if self._is_moving_selection:
            self._move_selection(event)
            return

        self._current_mouse_x = float(event.mouse_region_x)
        self._current_mouse_y = float(event.mouse_region_y)
        if not self._drag_started:
            if self._drag_distance(event) < _get_mask_drag_threshold(context):
                return
            self._begin_outside_drag(context, event)
            return

        if self._outside_drag_mode == "LASSO":
            self._append_path_point(event)
        self._tag_redraw()

    def _begin_outside_drag(self, context, event) -> None:
        settings = context.window_manager.zbrush_navigation_settings
        self._outside_drag_mode = settings.pen_outside_drag_mode
        self._drag_started = True
        if self._outside_drag_mode == "LASSO":
            self._append_path_point_from_coords(self._start_mouse_x, self._start_mouse_y, 0.0, force=True)
            self._append_path_point(event, force=True)
            self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(_draw_pen_outside_lasso_overlay, (self,), "WINDOW", "POST_PIXEL")
        elif self._outside_drag_mode == "BOX":
            self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(_draw_pen_outside_box_overlay, (self,), "WINDOW", "POST_PIXEL")
        else:
            raise RuntimeError(f"Unsupported Pen Outside Drag mode: {self._outside_drag_mode}")
        self._tag_redraw()

    def _finish_outside_drag(self, context, event):
        if self._is_moving_selection:
            self._move_selection(event)
        else:
            self._current_mouse_x = float(event.mouse_region_x)
            self._current_mouse_y = float(event.mouse_region_y)

        if self._outside_drag_mode == "LASSO":
            if not self._is_moving_selection:
                self._append_path_point(event, force=True)
            path = list(self._path)
            self._cleanup()
            if _lasso_hits_active_object(context, self._region, self._region_3d, path):
                _apply_native_lasso_mask(path, _drag_mask_value(event))
            else:
                _handle_empty_drag(context)
            return {"FINISHED"}

        if self._outside_drag_mode == "BOX":
            start = (self._start_mouse_x, self._start_mouse_y)
            end = (self._current_mouse_x, self._current_mouse_y)
            self._cleanup()
            if _box_hits_active_object(context, self._region, self._region_3d, start, end):
                _apply_native_box_mask(start, end, _drag_mask_value(event))
            else:
                _handle_empty_drag(context)
            return {"FINISHED"}

        self._cleanup()
        raise RuntimeError(f"Unsupported Pen Outside Drag mode: {self._outside_drag_mode}")

    def _handle_click(self):
        self._cleanup()
        _invert_mask()
        return {"FINISHED"}

    def _append_path_point(self, event, *, force: bool = False) -> bool:
        return self._append_path_point_from_coords(
            float(event.mouse_region_x),
            float(event.mouse_region_y),
            perf_counter() - self._start_time,
            force=force,
        )

    def _append_path_point_from_coords(self, x: float, y: float, elapsed: float, *, force: bool = False) -> bool:
        point = (x, y, elapsed)
        if self._path and not force:
            last_x, last_y, _last_time = self._path[-1]
            if hypot(point[0] - last_x, point[1] - last_y) < LASSO_MIN_POINT_DISTANCE_PIXELS:
                return False
        self._path.append(point)
        return True

    def _update_subtract_mode(self, event) -> None:
        is_subtracting = _event_is_subtracting(event)
        if self._is_subtracting == is_subtracting:
            return
        self._is_subtracting = is_subtracting
        if self._draw_handler is not None:
            self._tag_redraw()

    def _handle_space_event(self, event) -> None:
        if event.value == "PRESS":
            self._is_moving_selection = True
            self._move_mouse_x, self._move_mouse_y = _event_mouse_coords(event, self._current_mouse_x, self._current_mouse_y)
        elif event.value == "RELEASE":
            self._is_moving_selection = False

    def _move_selection(self, event) -> None:
        mouse_x, mouse_y, delta_x, delta_y = _event_mouse_delta(event, self._move_mouse_x, self._move_mouse_y)
        if delta_x == 0.0 and delta_y == 0.0:
            return

        if self._outside_drag_mode == "LASSO":
            self._path = _translate_lasso_path(self._path, delta_x, delta_y)
        elif self._outside_drag_mode == "BOX":
            self._start_mouse_x += delta_x
            self._start_mouse_y += delta_y
        else:
            raise RuntimeError(f"Unsupported Pen Outside Drag mode: {self._outside_drag_mode}")

        self._current_mouse_x += delta_x
        self._current_mouse_y += delta_y
        self._move_mouse_x = mouse_x
        self._move_mouse_y = mouse_y
        self._tag_redraw()

    def _drag_distance(self, event) -> float:
        return hypot(event.mouse_region_x - self._start_mouse_x, event.mouse_region_y - self._start_mouse_y)

    def _cleanup(self) -> None:
        if self._draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, "WINDOW")
            self._draw_handler = None
        self._tag_redraw()

    def _tag_redraw(self) -> None:
        if self._area is not None:
            self._area.tag_redraw()


class ZNAV_OT_mask_filter_click(bpy.types.Operator):
    bl_idname = "zbrush_navigation.mask_filter_click"
    bl_label = "ZBrush Mask Filter Click"
    bl_description = "Smooth or sharpen mask when Ctrl-clicking the active sculpt object"
    bl_options = {"REGISTER", "UNDO"}

    value: bpy.props.FloatProperty(default=1.0)

    @classmethod
    def poll(cls, context):
        return _can_use_sculpt_mask(context)

    def invoke(self, context, event):
        if not _event_hits_active_object(context, event):
            return {"PASS_THROUGH"}
        return _apply_mask_filter_click(self.value)


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
    _start_mouse_x = 0.0
    _start_mouse_y = 0.0
    _max_drag_distance = 0.0
    _start_hits_active_object = False
    _is_subtracting = False
    _is_moving_selection = False
    _move_mouse_x = 0.0
    _move_mouse_y = 0.0

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
        self._start_mouse_x = float(event.mouse_region_x)
        self._start_mouse_y = float(event.mouse_region_y)
        self._max_drag_distance = 0.0
        self._is_subtracting = _event_is_subtracting(event)
        self._is_moving_selection = False
        self._move_mouse_x = self._start_mouse_x
        self._move_mouse_y = self._start_mouse_y
        self._append_path_point(event)
        self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(_draw_lasso_overlay, (self,), "WINDOW", "POST_PIXEL")
        context.window_manager.modal_handler_add(self)
        self._tag_redraw()
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._cleanup()
            return {"CANCELLED"}

        self._update_subtract_mode(event)

        if event.type == "SPACE" and self._can_move_selection(context):
            self._handle_space_event(event)
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            if self._is_moving_selection:
                self._move_selection(event)
                return {"RUNNING_MODAL"}

            self._update_drag_distance(event)
            if self._append_path_point(event):
                self._tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if self._is_moving_selection:
                self._move_selection(event)
            else:
                self._append_path_point(event, force=True)
            return self._finish_lasso(context, event)

        return {"RUNNING_MODAL"}

    def _append_path_point(self, event, *, force: bool = False) -> bool:
        point = (float(event.mouse_region_x), float(event.mouse_region_y), perf_counter() - self._start_time)
        if self._path and not force:
            last_x, last_y, _last_time = self._path[-1]
            if hypot(point[0] - last_x, point[1] - last_y) < LASSO_MIN_POINT_DISTANCE_PIXELS:
                return False
        self._path.append(point)
        return True

    def _update_drag_distance(self, event) -> None:
        distance = hypot(event.mouse_region_x - self._start_mouse_x, event.mouse_region_y - self._start_mouse_y)
        self._max_drag_distance = max(self._max_drag_distance, distance)

    def _update_subtract_mode(self, event) -> None:
        is_subtracting = _event_is_subtracting(event)
        if self._is_subtracting == is_subtracting:
            return
        self._is_subtracting = is_subtracting
        self._tag_redraw()

    def _can_move_selection(self, context) -> bool:
        return len(self._path) >= 3 and self._max_drag_distance >= _get_mask_drag_threshold(context)

    def _handle_space_event(self, event) -> None:
        if event.value == "PRESS":
            self._is_moving_selection = True
            self._move_mouse_x, self._move_mouse_y = _event_mouse_coords(event, self._start_mouse_x, self._start_mouse_y)
        elif event.value == "RELEASE":
            self._is_moving_selection = False

    def _move_selection(self, event) -> None:
        mouse_x, mouse_y, delta_x, delta_y = _event_mouse_delta(event, self._move_mouse_x, self._move_mouse_y)
        if delta_x == 0.0 and delta_y == 0.0:
            return

        self._path = _translate_lasso_path(self._path, delta_x, delta_y)
        self._start_mouse_x += delta_x
        self._start_mouse_y += delta_y
        self._move_mouse_x = mouse_x
        self._move_mouse_y = mouse_y
        self._tag_redraw()

    def _finish_lasso(self, context, event):
        path = list(self._path)
        self._cleanup()

        if self._max_drag_distance < _get_mask_drag_threshold(context) or len(path) < 3:
            return self._handle_click(context)

        if _lasso_hits_active_object(context, self._region, self._region_3d, path):
            _apply_native_lasso_mask(path, _drag_mask_value(event))
            return {"FINISHED"}

        _handle_empty_drag(context)
        return {"FINISHED"}

    def _handle_click(self, context):
        if self._start_hits_active_object:
            return _apply_mask_filter_click(self.value)
        _invert_mask()
        return {"FINISHED"}

    def _cleanup(self) -> None:
        if self._draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, "WINDOW")
            self._draw_handler = None
        self._tag_redraw()

    def _tag_redraw(self) -> None:
        if self._area is not None:
            self._area.tag_redraw()


def _event_is_subtracting(event) -> bool:
    return bool(getattr(event, "alt", False))


def _drag_mask_value(event) -> float:
    return 0.0 if _event_is_subtracting(event) else 1.0


def _event_mouse_coords(event, fallback_x: float, fallback_y: float) -> tuple[float, float]:
    return float(getattr(event, "mouse_region_x", fallback_x)), float(getattr(event, "mouse_region_y", fallback_y))


def _event_mouse_delta(event, previous_x: float, previous_y: float) -> tuple[float, float, float, float]:
    mouse_x, mouse_y = _event_mouse_coords(event, previous_x, previous_y)
    return mouse_x, mouse_y, mouse_x - previous_x, mouse_y - previous_y


def _translate_lasso_path(path: list[tuple[float, float, float]], delta_x: float, delta_y: float) -> list[tuple[float, float, float]]:
    return [(x + delta_x, y + delta_y, elapsed) for x, y, elapsed in path]


def _get_mask_drag_threshold(context) -> float:
    addon_id = __package__.rsplit(".", 1)[0]
    addon = context.preferences.addons.get(addon_id)
    if addon is None:
        return DEFAULT_MASK_DRAG_THRESHOLD_PIXELS
    return addon.preferences.mask_drag_threshold_pixels


def _clear_mask() -> None:
    bpy.ops.paint.mask_flood_fill(mode="VALUE", value=0.0)


def _invert_mask() -> None:
    bpy.ops.paint.mask_flood_fill(mode="INVERT")


def _handle_empty_drag(context) -> None:
    if _should_voxel_remesh_on_empty_drag(context):
        _run_empty_drag_voxel_remesh(context)
        return
    _clear_mask()


def _should_voxel_remesh_on_empty_drag(context) -> bool:
    settings = context.window_manager.zbrush_navigation_settings
    obj = context.active_object
    return bool(settings.enable_empty_drag_voxel_remesh and obj is not None and not _object_has_sculpt_mask(obj))


def _object_has_sculpt_mask(obj) -> bool:
    mask_attribute = obj.data.attributes.get(".sculpt_mask")
    if mask_attribute is None:
        return False
    return any(mask_value.value > MASK_VALUE_EPSILON for mask_value in mask_attribute.data)


def _run_empty_drag_voxel_remesh(context) -> None:
    obj = context.active_object
    if obj is None:
        raise RuntimeError("Cannot voxel remesh without an active object")

    from .multires import _find_multires_modifier, _temporary_object_mode

    bpy.ops.ed.undo_push(message="Before ZBrush Navigation Empty Drag Voxel Remesh")

    with _temporary_object_mode(obj):
        context.view_layer.objects.active = obj
        obj.select_set(True)
        multires_modifier = _find_multires_modifier(obj)
        if multires_modifier is not None:
            multires_modifier.levels = multires_modifier.sculpt_levels
            bpy.ops.object.modifier_apply(modifier=multires_modifier.name)
        bpy.ops.object.voxel_remesh()


def _apply_mask_filter_click(value: float) -> set[str]:
    if value == 1.0:
        bpy.ops.sculpt.mask_filter(filter_type="SMOOTH")
        return {"FINISHED"}
    if value == 0.0:
        bpy.ops.sculpt.mask_filter(filter_type="SHARPEN")
        return {"FINISHED"}
    raise RuntimeError(f"Unsupported mask filter click value: {value}")


def _draw_lasso_overlay(operator: ZNAV_OT_mask_lasso_input) -> None:
    _draw_filled_polygon_overlay([(point[0], point[1]) for point in operator._path], *_mask_overlay_colors(operator))


def _draw_pen_outside_lasso_overlay(operator: ZNAV_OT_mask_pen_input) -> None:
    _draw_filled_polygon_overlay([(point[0], point[1]) for point in operator._path], *_mask_overlay_colors(operator))


def _draw_pen_outside_box_overlay(operator: ZNAV_OT_mask_pen_input) -> None:
    start = (operator._start_mouse_x, operator._start_mouse_y)
    end = (operator._current_mouse_x, operator._current_mouse_y)
    _draw_filled_polygon_overlay(_get_box_polygon(start, end), *_mask_overlay_colors(operator))


def _mask_overlay_colors(operator) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    if operator._is_subtracting:
        return SUBTRACT_MASK_OVERLAY_FILL_COLOR, SUBTRACT_MASK_OVERLAY_OUTLINE_COLOR
    return ADD_MASK_OVERLAY_FILL_COLOR, ADD_MASK_OVERLAY_OUTLINE_COLOR


def _draw_filled_polygon_overlay(
    coords: list[tuple[float, float]],
    fill_color: tuple[float, float, float, float],
    outline_color: tuple[float, float, float, float],
) -> None:
    if len(coords) < 2:
        return

    import gpu
    from gpu_extras.batch import batch_for_shader
    from mathutils import Vector
    from mathutils.geometry import tessellate_polygon

    closed_coords = coords + [coords[0]]
    shader = gpu.shader.from_builtin("UNIFORM_COLOR")

    gpu.state.blend_set("ALPHA")
    if len(coords) >= 3:
        polygon = [[Vector((x, y, 0.0)) for x, y in coords]]
        indices = tessellate_polygon(polygon)
        fill_batch = batch_for_shader(shader, "TRIS", {"pos": coords}, indices=indices)
        shader.bind()
        shader.uniform_float("color", fill_color)
        fill_batch.draw(shader)

    outline_batch = batch_for_shader(shader, "LINE_STRIP", {"pos": closed_coords})
    gpu.state.line_width_set(1.0)
    shader.bind()
    shader.uniform_float("color", outline_color)
    outline_batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set("NONE")


def _apply_native_lasso_mask(path: list[tuple[float, float, float]], value: float) -> None:
    operator_path = [
        {"name": str(index), "loc": (point[0], point[1]), "time": point[2]}
        for index, point in enumerate(path)
    ]
    bpy.ops.paint.mask_lasso_gesture(path=operator_path, mode="VALUE", value=value)


def _apply_native_box_mask(start: tuple[float, float], end: tuple[float, float], value: float) -> None:
    min_x, max_x, min_y, max_y = _box_bounds(start, end)
    bpy.ops.paint.mask_box_gesture(
        xmin=int(min_x),
        xmax=int(max_x),
        ymin=int(min_y),
        ymax=int(max_y),
        wait_for_input=False,
        mode="VALUE",
        value=value,
    )


def _lasso_hits_active_object(context, region, region_3d, path: list[tuple[float, float, float]]) -> bool:
    polygon = [(point[0], point[1]) for point in path]
    return _polygon_hits_active_object(context, region, region_3d, polygon)


def _box_hits_active_object(
    context,
    region,
    region_3d,
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    return _polygon_hits_active_object(context, region, region_3d, _get_box_polygon(start, end))


def _polygon_hits_active_object(context, region, region_3d, polygon: list[tuple[float, float]]) -> bool:
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


def _get_box_polygon(start: tuple[float, float], end: tuple[float, float]) -> list[tuple[float, float]]:
    min_x, max_x, min_y, max_y = _box_bounds(start, end)
    return [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]


def _box_bounds(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float, float, float]:
    return min(start[0], end[0]), max(start[0], end[0]), min(start[1], end[1]), max(start[1], end[1])


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
