from __future__ import annotations

from dataclasses import dataclass

from mathutils import Quaternion, Vector


@dataclass(frozen=True)
class AxisView:
    name: str
    direction: Vector


AXIS_VIEWS = (
    AxisView("FRONT", Vector((0.0, -1.0, 0.0))),
    AxisView("BACK", Vector((0.0, 1.0, 0.0))),
    AxisView("RIGHT", Vector((-1.0, 0.0, 0.0))),
    AxisView("LEFT", Vector((1.0, 0.0, 0.0))),
    AxisView("TOP", Vector((0.0, 0.0, -1.0))),
    AxisView("BOTTOM", Vector((0.0, 0.0, 1.0))),
)


def get_view_direction(view_rotation: Quaternion) -> Vector:
    direction = view_rotation @ Vector((0.0, 0.0, -1.0))
    if direction.length == 0.0:
        raise ValueError("Cannot snap view with a zero-length view direction")
    return direction.normalized()


def get_nearest_axis_view(view_rotation: Quaternion) -> AxisView:
    return get_nearest_axis_view_from_direction(get_view_direction(view_rotation))


def get_nearest_axis_view_from_direction(direction: Vector) -> AxisView:
    if direction.length == 0.0:
        raise ValueError("Cannot find nearest axis from a zero-length direction")
    normalized_direction = direction.normalized()
    return max(AXIS_VIEWS, key=lambda axis_view: normalized_direction.dot(axis_view.direction))


def get_axis_view_rotation(axis_view: AxisView) -> Quaternion:
    return axis_view.direction.to_track_quat("-Z", "Y")


def get_next_axis_view_from_drag(axis_view: AxisView, delta_x: float, delta_y: float) -> AxisView:
    if delta_x == 0.0 and delta_y == 0.0:
        return axis_view

    view_rotation = get_axis_view_rotation(axis_view)
    screen_right = view_rotation @ Vector((1.0, 0.0, 0.0))
    screen_up = view_rotation @ Vector((0.0, 1.0, 0.0))
    if abs(delta_x) >= abs(delta_y):
        target_direction = screen_right if delta_x > 0.0 else -screen_right
    else:
        target_direction = screen_up if delta_y > 0.0 else -screen_up
    return get_nearest_axis_view_from_direction(target_direction)


def snap_region_3d_to_axis(region_3d, axis_view: AxisView) -> AxisView:
    view_perspective = region_3d.view_perspective
    region_3d.view_rotation = get_axis_view_rotation(axis_view)
    region_3d.view_perspective = view_perspective
    return axis_view


def snap_region_3d_to_nearest_axis(region_3d) -> AxisView:
    axis_view = get_nearest_axis_view(region_3d.view_rotation)
    return snap_region_3d_to_axis(region_3d, axis_view)