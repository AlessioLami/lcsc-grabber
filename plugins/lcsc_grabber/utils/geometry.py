import math
from typing import Tuple, List, Optional


EASYEDA_UNIT_TO_MM = 0.254
MIL_TO_MM = 0.0254


def mil_to_mm(value: float) -> float:
    return value * MIL_TO_MM


def easyeda_to_mm(value: float) -> float:
    return value * EASYEDA_UNIT_TO_MM


def mm_to_easyeda(value: float) -> float:
    return value / EASYEDA_UNIT_TO_MM


def flip_y(y: float) -> float:
    return -y


def transform_point(
    x: float,
    y: float,
    offset_x: float = 0,
    offset_y: float = 0,
    scale: float = 1.0,
    flip_y_axis: bool = True
) -> Tuple[float, float]:
    new_x = (x * scale) + offset_x
    new_y = (y * scale) + offset_y

    if flip_y_axis:
        new_y = -new_y

    return (new_x, new_y)


def transform_points(
    points: List[Tuple[float, float]],
    offset_x: float = 0,
    offset_y: float = 0,
    scale: float = 1.0,
    flip_y_axis: bool = True
) -> List[Tuple[float, float]]:
    return [
        transform_point(x, y, offset_x, offset_y, scale, flip_y_axis)
        for x, y in points
    ]


def rotate_point(
    x: float,
    y: float,
    angle_deg: float,
    cx: float = 0,
    cy: float = 0
) -> Tuple[float, float]:
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)

    dx = x - cx
    dy = y - cy

    new_x = dx * cos_a - dy * sin_a
    new_y = dx * sin_a + dy * cos_a

    return (new_x + cx, new_y + cy)


def normalize_angle(angle: float) -> float:
    while angle < 0:
        angle += 360
    while angle >= 360:
        angle -= 360
    return angle


def easyeda_rotation_to_kicad(rotation: float) -> float:
    return normalize_angle(-rotation)


def parse_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def parse_int(value: str, default: int = 0) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def round_to_grid(value: float, grid: float = 0.01) -> float:
    return round(value / grid) * grid


def format_mm(value: float, precision: int = 4) -> str:
    formatted = f"{value:.{precision}f}"
    if '.' in formatted:
        formatted = formatted.rstrip('0').rstrip('.')
    return formatted


def calculate_arc_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    start_angle: float,
    end_angle: float,
    num_points: int = 32
) -> List[Tuple[float, float]]:
    points = []

    if end_angle < start_angle:
        end_angle += 360

    angle_range = end_angle - start_angle

    for i in range(num_points + 1):
        t = i / num_points
        angle = math.radians(start_angle + t * angle_range)
        x = cx + rx * math.cos(angle)
        y = cy + ry * math.sin(angle)
        points.append((x, y))

    return points


def bounding_box(
    points: List[Tuple[float, float]]
) -> Tuple[float, float, float, float]:
    if not points:
        return (0, 0, 0, 0)

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    return (min(xs), min(ys), max(xs), max(ys))


def expand_bbox(
    bbox: Tuple[float, float, float, float],
    margin: float
) -> Tuple[float, float, float, float]:
    return (
        bbox[0] - margin,
        bbox[1] - margin,
        bbox[2] + margin,
        bbox[3] + margin
    )
