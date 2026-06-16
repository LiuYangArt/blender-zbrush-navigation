from __future__ import annotations

from math import hypot
from time import perf_counter

import bpy
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d

from .mask import (
    LASSO_HIT_TEST_MIN_STEP_PIXELS,
    LASSO_MIN_POINT_DISTANCE_PIXELS,
    ADD_MASK_OVERLAY_FILL_COLOR,
    ADD_MASK_OVERLAY_OUTLINE_COLOR,
    SELECTION_TARGET_FACESET,
    SELECTION_TARGET_MASK,
    SUBTRACT_MASK_OVERLAY_FILL_COLOR,
    SUBTRACT_MASK_OVERLAY_OUTLINE_COLOR,
    _apply_native_box_mask,
    _apply_native_lasso_mask,
    _box_hits_active_object,
    _draw_filled_polygon_overlay,
    _event_mouse_coords,
    _event_mouse_delta,
    _get_box_polygon,
    _get_mask_drag_threshold,
    _handle_empty_drag,
    _lasso_hits_active_object,
    _screen_point_hits_active_object,
    _translate_lasso_path,
    _event_is_selection_target_toggle,
    _next_selection_target,
    _can_use_sculpt_mask,
)


FACESET_ADD_OVERLAY_FILL_COLOR = (0.0, 0.85, 0.25, 0.28)
FACESET_HIDE_OVERLAY_FILL_COLOR = (1.0, 0.05, 0.02, 0.28)
FACESET_OVERLAY_OUTLINE_COLOR = (1.0, 1.0, 1.0, 0.75)
FACE_SET_ATTRIBUTE_NAMES = (".sculpt_face_set", "sculpt_face_set")
HIDE_POLY_ATTRIBUTE_NAME = ".hide_poly"


class ZNAV_OT_faceset_polygroup_input(bpy.types.Operator):
    bl_idname = "zbrush_navigation.faceset_polygroup_input"
    bl_label = "ZBrush Face Set Polygroup Input"
    bl_description = "Use Ctrl+Shift click/drag for ZBrush-style Face Set visibility and creation"
    bl_options = {"REGISTER", "UNDO"}

    _area = None
    _region = None
    _region_3d = None
    _draw_handler = None
    _start_mouse_x = 0.0
    _start_mouse_y = 0.0
    _current_mouse_x = 0.0
    _current_mouse_y = 0.0
    _drag_started = False
    _is_hiding = False
    _is_moving_selection = False
    _move_mouse_x = 0.0
    _move_mouse_y = 0.0
    _path = None
    _start_time = 0.0
    _gesture_mode = None
    _selection_target = SELECTION_TARGET_FACESET

    @classmethod
    def poll(cls, context):
        return _can_use_sculpt_mask(context)

    def invoke(self, context, event):
        self._area = context.area
        self._region = context.region
        self._region_3d = context.space_data.region_3d
        self._draw_handler = None
        self._start_mouse_x = float(event.mouse_region_x)
        self._start_mouse_y = float(event.mouse_region_y)
        self._current_mouse_x = self._start_mouse_x
        self._current_mouse_y = self._start_mouse_y
        self._drag_started = False
        self._is_hiding = _event_is_hiding(event)
        self._is_moving_selection = False
        self._move_mouse_x = self._start_mouse_x
        self._move_mouse_y = self._start_mouse_y
        self._path = []
        self._start_time = perf_counter()
        self._selection_target = SELECTION_TARGET_FACESET
        self._gesture_mode = None
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if event.type == "ESC":
            self._cleanup()
            return {"CANCELLED"}

        if _event_is_selection_target_toggle(event) and self._can_toggle_selection_target():
            self._toggle_selection_target()
            return {"RUNNING_MODAL"}

        self._update_hiding_mode(event)

        if event.type == "SPACE" and self._drag_started:
            self._handle_space_event(event)
            return {"RUNNING_MODAL"}

        if event.type == "MOUSEMOVE":
            self._handle_mouse_move(context, event)
            return {"RUNNING_MODAL"}

        if event.type == "LEFTMOUSE" and event.value == "RELEASE":
            if self._drag_started:
                return self._finish_drag(context, event)
            return self._handle_click(context, event)

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
            self._begin_drag(context, event)
            return

        if self._gesture_mode in {"LASSO", "POLYLINE"}:
            self._append_path_point(event)
        self._tag_redraw()

    def _begin_drag(self, context, event) -> None:
        self._gesture_mode = context.window_manager.zbrush_navigation_settings.faceset_gesture
        self._drag_started = True
        if self._gesture_mode in {"LASSO", "POLYLINE"}:
            self._append_path_point_from_coords(self._start_mouse_x, self._start_mouse_y, 0.0, force=True)
            self._append_path_point(event, force=True)
        if self._gesture_mode not in {"BOX", "LASSO", "LINE", "POLYLINE"}:
            raise RuntimeError(f"Unsupported Face Set Gesture mode: {self._gesture_mode}")
        self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(_draw_faceset_overlay, (self,), "WINDOW", "POST_PIXEL")
        self._tag_redraw()

    def _finish_drag(self, context, event):
        if self._is_moving_selection:
            self._move_selection(event)
        else:
            self._current_mouse_x = float(event.mouse_region_x)
            self._current_mouse_y = float(event.mouse_region_y)
            if self._gesture_mode in {"LASSO", "POLYLINE"}:
                self._append_path_point(event, force=True)

        gesture_mode = self._gesture_mode
        start = (self._start_mouse_x, self._start_mouse_y)
        end = (self._current_mouse_x, self._current_mouse_y)
        path = list(self._path)
        region = self._region
        region_3d = self._region_3d
        front_faces_only = context.window_manager.zbrush_navigation_settings.faceset_front_faces_only
        limit_to_segment = context.window_manager.zbrush_navigation_settings.faceset_line_limit_to_segment
        self._cleanup()

        if self._selection_target == SELECTION_TARGET_MASK:
            _finish_mask_from_faceset(context, region, region_3d, gesture_mode, start, end, path, event)
            return {"FINISHED"}

        if not _gesture_hits_active_object(context, region, region_3d, gesture_mode, start, end, path):
            _invert_visibility_if_any_hidden(context.active_object)
            return {"FINISHED"}

        _apply_native_faceset_gesture(gesture_mode, start, end, path, front_faces_only, limit_to_segment)
        return {"FINISHED"}

    def _handle_click(self, context, event):
        mouse = (float(event.mouse_region_x), float(event.mouse_region_y))
        face_index = _raycast_active_face_index(context, self._region, self._region_3d, mouse)
        self._cleanup()
        if face_index is None:
            _show_all_visibility()
            return {"FINISHED"}
        active_object = context.active_object
        face_set_id = _get_face_set_id(active_object, face_index)
        _apply_faceset_visibility_click(active_object, face_set_id, _event_is_hiding(event))
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

    def _update_hiding_mode(self, event) -> None:
        is_hiding = _event_is_hiding(event)
        if self._is_hiding == is_hiding:
            return
        self._is_hiding = is_hiding
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

        if self._gesture_mode in {"LASSO", "POLYLINE"}:
            self._path = _translate_lasso_path(self._path, delta_x, delta_y)
        else:
            self._start_mouse_x += delta_x
            self._start_mouse_y += delta_y

        self._current_mouse_x += delta_x
        self._current_mouse_y += delta_y
        self._move_mouse_x = mouse_x
        self._move_mouse_y = mouse_y
        self._tag_redraw()

    def _drag_distance(self, event) -> float:
        return hypot(event.mouse_region_x - self._start_mouse_x, event.mouse_region_y - self._start_mouse_y)

    def _can_toggle_selection_target(self) -> bool:
        return self._drag_started and self._gesture_mode in {"BOX", "LASSO"}

    def _toggle_selection_target(self) -> None:
        self._selection_target = _next_selection_target(self._selection_target)
        self._tag_redraw()

    def _cleanup(self) -> None:
        if self._draw_handler is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, "WINDOW")
            self._draw_handler = None
        self._tag_redraw()

    def _tag_redraw(self) -> None:
        if self._area is not None:
            self._area.tag_redraw()


def _event_is_hiding(event) -> bool:
    return bool(getattr(event, "alt", False))


def _draw_faceset_overlay(operator: ZNAV_OT_faceset_polygroup_input) -> None:
    if operator._gesture_mode == "BOX":
        coords = _get_box_polygon((operator._start_mouse_x, operator._start_mouse_y), (operator._current_mouse_x, operator._current_mouse_y))
    elif operator._gesture_mode in {"LASSO", "POLYLINE"}:
        coords = [(point[0], point[1]) for point in operator._path]
    elif operator._gesture_mode == "LINE":
        coords = [(operator._start_mouse_x, operator._start_mouse_y), (operator._current_mouse_x, operator._current_mouse_y)]
    else:
        return
    _draw_filled_polygon_overlay(coords, *_faceset_overlay_colors(operator))


def _faceset_overlay_colors(operator) -> tuple[tuple[float, float, float, float], tuple[float, float, float, float]]:
    if operator._selection_target == SELECTION_TARGET_MASK:
        if operator._is_hiding:
            return SUBTRACT_MASK_OVERLAY_FILL_COLOR, SUBTRACT_MASK_OVERLAY_OUTLINE_COLOR
        return ADD_MASK_OVERLAY_FILL_COLOR, ADD_MASK_OVERLAY_OUTLINE_COLOR
    fill_color = FACESET_HIDE_OVERLAY_FILL_COLOR if operator._is_hiding else FACESET_ADD_OVERLAY_FILL_COLOR
    return fill_color, FACESET_OVERLAY_OUTLINE_COLOR


def _gesture_hits_active_object(context, region, region_3d, gesture_mode, start, end, path) -> bool:
    if gesture_mode == "BOX":
        return _box_hits_active_object(context, region, region_3d, start, end)
    if gesture_mode == "LINE":
        return _line_hits_active_object(context, region, region_3d, start, end)
    if gesture_mode in {"LASSO", "POLYLINE"}:
        if len(path) < 3:
            return _line_hits_active_object(context, region, region_3d, start, end)
        return _lasso_hits_active_object(context, region, region_3d, path)
    raise RuntimeError(f"Unsupported Face Set Gesture mode: {gesture_mode}")


def _line_hits_active_object(context, region, region_3d, start: tuple[float, float], end: tuple[float, float]) -> bool:
    distance = hypot(end[0] - start[0], end[1] - start[1])
    steps = max(1, int(distance / LASSO_HIT_TEST_MIN_STEP_PIXELS))
    for index in range(steps + 1):
        factor = index / steps
        point = (start[0] + (end[0] - start[0]) * factor, start[1] + (end[1] - start[1]) * factor)
        if _screen_point_hits_active_object(context, region, region_3d, point):
            return True
    return False


def _finish_mask_from_faceset(
    context,
    region,
    region_3d,
    gesture_mode: str,
    start: tuple[float, float],
    end: tuple[float, float],
    path: list[tuple[float, float, float]],
    event,
) -> None:
    if gesture_mode == "BOX":
        if _box_hits_active_object(context, region, region_3d, start, end):
            _apply_native_box_mask(start, end, _mask_value_from_faceset_event(event))
        else:
            _handle_empty_drag(context)
        return

    if gesture_mode == "LASSO":
        if _lasso_hits_active_object(context, region, region_3d, path):
            _apply_native_lasso_mask(path, _mask_value_from_faceset_event(event))
        else:
            _handle_empty_drag(context)
        return

    raise RuntimeError(f"Cannot switch Face Set gesture to Mask gesture: {gesture_mode}")


def _mask_value_from_faceset_event(event) -> float:
    return 0.0 if _event_is_hiding(event) else 1.0


def _apply_native_faceset_gesture(
    gesture_mode: str,
    start: tuple[float, float],
    end: tuple[float, float],
    path: list[tuple[float, float, float]],
    front_faces_only: bool,
    limit_to_segment: bool,
) -> None:
    if gesture_mode == "BOX":
        min_x, max_x = sorted((start[0], end[0]))
        min_y, max_y = sorted((start[1], end[1]))
        bpy.ops.sculpt.face_set_box_gesture(
            xmin=int(min_x),
            xmax=int(max_x),
            ymin=int(min_y),
            ymax=int(max_y),
            wait_for_input=False,
            use_front_faces_only=front_faces_only,
        )
        return

    operator_path = _to_operator_path(path)
    if gesture_mode == "LASSO":
        bpy.ops.sculpt.face_set_lasso_gesture(path=operator_path, use_front_faces_only=front_faces_only)
        return
    if gesture_mode == "POLYLINE":
        bpy.ops.sculpt.face_set_polyline_gesture(path=operator_path, use_front_faces_only=front_faces_only)
        return
    if gesture_mode == "LINE":
        bpy.ops.sculpt.face_set_line_gesture(
            xstart=int(start[0]),
            xend=int(end[0]),
            ystart=int(start[1]),
            yend=int(end[1]),
            flip=False,
            use_front_faces_only=front_faces_only,
            use_limit_to_segment=limit_to_segment,
        )
        return
    raise RuntimeError(f"Unsupported Face Set Gesture mode: {gesture_mode}")


def _to_operator_path(path: list[tuple[float, float, float]]) -> list[dict[str, object]]:
    return [{"name": str(index), "loc": (point[0], point[1]), "time": point[2]} for index, point in enumerate(path)]


def _apply_faceset_visibility_click(obj, face_set_id: int, is_hiding: bool) -> None:
    if is_hiding:
        _hide_faceset(face_set_id)
        return

    visible_face_sets, has_hidden_faces = _get_visible_face_set_ids(obj)
    if has_hidden_faces:
        if visible_face_sets == {face_set_id}:
            _invert_visibility()
            return
        _hide_faceset(face_set_id)
        return

    _show_all_visibility()
    bpy.ops.sculpt.face_set_change_visibility(mode="TOGGLE", active_face_set=face_set_id)


def _hide_faceset(face_set_id: int) -> None:
    bpy.ops.sculpt.face_set_change_visibility(mode="HIDE_ACTIVE", active_face_set=face_set_id)


def _get_visible_face_set_ids(obj) -> tuple[set[int], bool]:
    face_set_attribute = _get_face_set_attribute(obj)
    hidden_attribute = _get_hidden_face_attribute(obj)
    if hidden_attribute is not None and len(hidden_attribute.data) != len(face_set_attribute.data):
        raise RuntimeError(
            f"Hide attribute length {len(hidden_attribute.data)} does not match Face Set length {len(face_set_attribute.data)}"
        )

    visible_face_sets = set()
    has_hidden_faces = False
    for index, face_set_value in enumerate(face_set_attribute.data):
        is_hidden = hidden_attribute is not None and bool(hidden_attribute.data[index].value)
        has_hidden_faces = has_hidden_faces or is_hidden
        if not is_hidden:
            visible_face_sets.add(int(face_set_value.value))
    return visible_face_sets, has_hidden_faces


def _invert_visibility_if_any_hidden(obj) -> None:
    if _object_has_hidden_faces(obj):
        _invert_visibility()


def _object_has_hidden_faces(obj) -> bool:
    if obj is None:
        return False
    hidden_attribute = _get_hidden_face_attribute(obj)
    return hidden_attribute is not None and any(bool(face.value) for face in hidden_attribute.data)


def _invert_visibility() -> None:
    bpy.ops.paint.visibility_invert()


def _show_all_visibility() -> None:
    bpy.ops.paint.hide_show_all(action="SHOW")


def _raycast_active_face_index(context, region, region_3d, mouse: tuple[float, float]) -> int | None:
    origin = region_2d_to_origin_3d(region, region_3d, mouse)
    direction = region_2d_to_vector_3d(region, region_3d, mouse)
    depsgraph = context.evaluated_depsgraph_get()
    hit, _location, _normal, face_index, hit_object, _matrix = context.scene.ray_cast(depsgraph, origin, direction)
    if not hit or hit_object != context.active_object:
        return None
    return face_index


def _get_face_set_id(obj, face_index: int) -> int:
    if obj is None:
        raise RuntimeError("Cannot read Face Set id without an active object")
    if face_index < 0:
        raise RuntimeError(f"Cannot read Face Set id from invalid face index: {face_index}")

    attribute = _get_face_set_attribute(obj)
    if face_index >= len(attribute.data):
        raise RuntimeError(f"Face index {face_index} is outside Face Set attribute length {len(attribute.data)}")
    return int(attribute.data[face_index].value)


def _get_hidden_face_attribute(obj):
    attribute = obj.data.attributes.get(HIDE_POLY_ATTRIBUTE_NAME)
    if attribute is not None and attribute.domain != "FACE":
        raise RuntimeError(f"Unexpected hide attribute domain: {attribute.domain}")
    return attribute


def _get_face_set_attribute(obj):
    attribute = None
    for name in FACE_SET_ATTRIBUTE_NAMES:
        attribute = obj.data.attributes.get(name)
        if attribute is not None:
            break
    if attribute is None:
        raise RuntimeError(f"Cannot find Sculpt Face Set attribute; tried {FACE_SET_ATTRIBUTE_NAMES}")
    if attribute.domain != "FACE":
        raise RuntimeError(f"Unexpected Face Set attribute domain: {attribute.domain}")
    return attribute
