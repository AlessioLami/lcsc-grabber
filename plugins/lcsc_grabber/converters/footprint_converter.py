import re
import json
import logging
import math
from typing import Optional, List, Dict, Any, Tuple

from ..api.models import (
    EasyEdaFootprint, FootprintPad, FootprintLine, FootprintCircle,
    FootprintArc, FootprintPolygon, FootprintText, FootprintHole,
    Point, PadShape, PadType, get_kicad_layer
)
from ..utils.geometry import (
    easyeda_to_mm, mil_to_mm, parse_float, parse_int, normalize_angle,
    bounding_box, expand_bbox
)


logger = logging.getLogger(__name__)


class FootprintConverter:

    SCALE = 0.254

    PAD_SHAPE_MAP = {
        "ELLIPSE": PadShape.CIRCLE,
        "OVAL": PadShape.OVAL,
        "RECT": PadShape.RECT,
        "POLYGON": PadShape.CUSTOM,
        "ROUND": PadShape.CIRCLE,
    }

    def __init__(self):
        self.current_footprint: Optional[EasyEdaFootprint] = None

    def convert(
        self,
        footprint_data: Dict[str, Any],
        component_name: str = "Footprint"
    ) -> Optional[EasyEdaFootprint]:
        try:
            self.current_footprint = EasyEdaFootprint(name=component_name)

            if isinstance(footprint_data, str):
                try:
                    footprint_data = json.loads(footprint_data)
                except json.JSONDecodeError:
                    logger.error("Failed to parse footprint data as JSON")
                    return None

            self._parse_footprint_data(footprint_data)

            self._calculate_bounds_and_center()

            self._calculate_bounds()

            if not self.current_footprint.has_courtyard():
                self._generate_courtyard()

            return self.current_footprint

        except Exception as e:
            logger.error(f"Error converting footprint: {e}", exc_info=True)
            return None

    def _parse_footprint_data(self, data: Dict[str, Any]):
        shapes = data.get("shape") or data.get("shapes") or []
        if isinstance(shapes, str):
            shapes = shapes.split("#@$")

        for shape in shapes:
            if isinstance(shape, str):
                self._parse_shape_string(shape)
            elif isinstance(shape, dict):
                self._parse_shape_dict(shape)

        if "dataStr" in data:
            nested = data["dataStr"]
            if isinstance(nested, str):
                try:
                    nested = json.loads(nested)
                except json.JSONDecodeError:
                    pass
            if isinstance(nested, dict):
                self._parse_footprint_data(nested)

    def _parse_shape_string(self, shape_str: str):
        if not shape_str or not isinstance(shape_str, str):
            return

        parts = shape_str.split("~")
        if not parts:
            return

        shape_type = parts[0].upper()

        try:
            if shape_type == "PAD":
                self._parse_pad(parts)
            elif shape_type == "TRACK":
                self._parse_track(parts)
            elif shape_type == "CIRCLE":
                self._parse_circle(parts)
            elif shape_type == "ARC":
                self._parse_arc(parts)
            elif shape_type == "RECT":
                self._parse_rect(parts)
            elif shape_type == "SOLIDREGION":
                self._parse_solid_region(parts)
            elif shape_type == "TEXT":
                self._parse_text(parts)
            elif shape_type == "HOLE":
                self._parse_hole(parts)
            elif shape_type == "VIA":
                self._parse_via(parts)
            elif shape_type == "SVGNODE":
                pass
        except Exception as e:
            logger.warning(f"Error parsing shape '{shape_type}': {e}")

    def _parse_shape_dict(self, shape: Dict[str, Any]):
        pass

    def _parse_pad(self, parts: List[str]):
        if len(parts) < 9:
            return

        try:
            shape_str = parts[1].upper()
            x = parse_float(parts[2]) * self.SCALE
            y = parse_float(parts[3]) * self.SCALE
            width = parse_float(parts[4]) * self.SCALE
            height = parse_float(parts[5]) * self.SCALE
            layer = parts[6]
            number = parts[8]

            shape = self.PAD_SHAPE_MAP.get(shape_str, PadShape.RECT)

            drill_size = 0
            pad_type = PadType.SMD

            if len(parts) > 9:
                hole_radius = parse_float(parts[9]) * self.SCALE
                if hole_radius > 0:
                    drill_size = hole_radius * 2
                    pad_type = PadType.THRU_HOLE

            rotation = 0
            if len(parts) > 11:
                rotation = parse_float(parts[11])

            kicad_layer = get_kicad_layer(layer)
            if pad_type == PadType.THRU_HOLE:
                layers = ["*.Cu", "*.Paste", "*.Mask"]
            elif kicad_layer.startswith("F."):
                layers = ["F.Cu", "F.Paste", "F.Mask"]
            else:
                layers = ["B.Cu", "B.Paste", "B.Mask"]

            pad = FootprintPad(
                number=str(number),
                x=x,
                y=-y,
                width=width,
                height=height,
                shape=shape,
                pad_type=pad_type,
                rotation=rotation,
                drill_size=drill_size,
                layers=layers
            )

            self.current_footprint.pads.append(pad)

        except Exception as e:
            logger.warning(f"Error parsing pad: {e}")

    def _parse_track(self, parts: List[str]):
        if len(parts) < 5:
            return

        try:
            stroke_width = parse_float(parts[1]) * self.SCALE
            layer = parts[2]
            points_str = parts[4]

            kicad_layer = get_kicad_layer(layer)

            points = self._parse_point_list(points_str)

            for i in range(len(points) - 1):
                line = FootprintLine(
                    x1=points[i][0],
                    y1=-points[i][1],
                    x2=points[i + 1][0],
                    y2=-points[i + 1][1],
                    layer=kicad_layer,
                    stroke_width=max(stroke_width, 0.1)
                )
                self.current_footprint.lines.append(line)

        except Exception as e:
            logger.warning(f"Error parsing track: {e}")

    def _parse_circle(self, parts: List[str]):
        if len(parts) < 6:
            return

        try:
            cx = parse_float(parts[1]) * self.SCALE
            cy = parse_float(parts[2]) * self.SCALE
            radius = parse_float(parts[3]) * self.SCALE
            stroke_width = parse_float(parts[4]) * self.SCALE
            layer = parts[5]

            kicad_layer = get_kicad_layer(layer)

            circle = FootprintCircle(
                cx=cx,
                cy=-cy,
                radius=radius,
                layer=kicad_layer,
                stroke_width=max(stroke_width, 0.1)
            )

            self.current_footprint.circles.append(circle)

        except Exception as e:
            logger.warning(f"Error parsing circle: {e}")

    def _parse_arc(self, parts: List[str]):
        if len(parts) < 5:
            return

        try:
            stroke_width = parse_float(parts[1]) * self.SCALE
            layer = parts[2]
            path_data = parts[4]

            kicad_layer = get_kicad_layer(layer)

            arc_params = self._parse_arc_path(path_data)
            if arc_params:
                cx, cy, radius, start_angle, end_angle = arc_params

                arc = FootprintArc(
                    cx=cx,
                    cy=-cy,
                    radius=radius,
                    start_angle=-end_angle,
                    end_angle=-start_angle,
                    layer=kicad_layer,
                    stroke_width=max(stroke_width, 0.1)
                )

                self.current_footprint.arcs.append(arc)

        except Exception as e:
            logger.warning(f"Error parsing arc: {e}")

    def _parse_rect(self, parts: List[str]):
        if len(parts) < 6:
            return

        try:
            x = parse_float(parts[1]) * self.SCALE
            y = parse_float(parts[2]) * self.SCALE
            width = parse_float(parts[3]) * self.SCALE
            height = parse_float(parts[4]) * self.SCALE
            layer = parts[5]

            kicad_layer = get_kicad_layer(layer)

            y_flipped = -y

            lines = [
                FootprintLine(x, y_flipped, x + width, y_flipped, kicad_layer),
                FootprintLine(x + width, y_flipped, x + width, y_flipped - height, kicad_layer),
                FootprintLine(x + width, y_flipped - height, x, y_flipped - height, kicad_layer),
                FootprintLine(x, y_flipped - height, x, y_flipped, kicad_layer),
            ]

            self.current_footprint.lines.extend(lines)

        except Exception as e:
            logger.warning(f"Error parsing rect: {e}")

    def _parse_solid_region(self, parts: List[str]):
        if len(parts) < 4:
            return

        try:
            layer = parts[1]
            path_str = parts[3]

            kicad_layer = get_kicad_layer(layer)

            if layer in ("99", "100", "101"):
                return

            points = self._parse_svg_path_points(path_str)
            if not points:
                return

            polygon = FootprintPolygon(
                points=[Point(p[0], -p[1]) for p in points],
                layer=kicad_layer
            )

            self.current_footprint.polygons.append(polygon)

        except Exception as e:
            logger.warning(f"Error parsing solid region: {e}")

    def _parse_svg_path_points(self, path_str: str) -> List[Tuple[float, float]]:
        points = []

        clean = re.sub(r'[MLZmlz]', ' ', path_str)
        values = re.split(r'[,\s]+', clean.strip())

        i = 0
        while i < len(values) - 1:
            try:
                x = parse_float(values[i]) * self.SCALE
                y = parse_float(values[i + 1]) * self.SCALE
                points.append((x, y))
                i += 2
            except (ValueError, IndexError):
                i += 1

        return points

    def _parse_text(self, parts: List[str]):
        if len(parts) < 11:
            return

        try:
            text_type_str = parts[1].lower()
            x = parse_float(parts[2]) * self.SCALE
            y = parse_float(parts[3]) * self.SCALE
            stroke_width = parse_float(parts[4]) * self.SCALE
            rotation = parse_float(parts[5])
            layer = parts[7]
            font_size = parse_float(parts[9]) * self.SCALE
            text_content = parts[10] if len(parts) > 10 else ""

            kicad_layer = get_kicad_layer(layer)

            if text_type_str in ("ref", "reference"):
                text_type = "reference"
                text_content = "REF**"
            elif text_type_str in ("val", "value"):
                text_type = "value"
            else:
                text_type = "user"

            text = FootprintText(
                text=text_content,
                x=x,
                y=-y,
                layer=kicad_layer,
                font_size=max(font_size, 0.5),
                thickness=max(stroke_width, 0.1),
                rotation=rotation,
                text_type=text_type
            )

            self.current_footprint.texts.append(text)

        except Exception as e:
            logger.warning(f"Error parsing text: {e}")

    def _parse_hole(self, parts: List[str]):
        if len(parts) < 4:
            return

        try:
            x = parse_float(parts[1]) * self.SCALE
            y = parse_float(parts[2]) * self.SCALE
            diameter = parse_float(parts[3]) * self.SCALE

            hole = FootprintHole(
                x=x,
                y=-y,
                diameter=diameter
            )

            self.current_footprint.holes.append(hole)

        except Exception as e:
            logger.warning(f"Error parsing hole: {e}")

    def _parse_via(self, parts: List[str]):
        if len(parts) < 5:
            return

        try:
            x = parse_float(parts[1]) * self.SCALE
            y = parse_float(parts[2]) * self.SCALE
            diameter = parse_float(parts[3]) * self.SCALE
            drill = parse_float(parts[4]) * self.SCALE

            pad = FootprintPad(
                number="",
                x=x,
                y=-y,
                width=diameter,
                height=diameter,
                shape=PadShape.CIRCLE,
                pad_type=PadType.THRU_HOLE,
                drill_size=drill,
                layers=["*.Cu"]
            )

            if drill > 0.1:
                self.current_footprint.pads.append(pad)

        except Exception as e:
            logger.warning(f"Error parsing via: {e}")

    def _parse_point_list(self, points_str: str) -> List[Tuple[float, float]]:
        points = []

        values = re.split(r'[,\s]+', points_str.strip())

        for i in range(0, len(values) - 1, 2):
            try:
                x = parse_float(values[i]) * self.SCALE
                y = parse_float(values[i + 1]) * self.SCALE
                points.append((x, y))
            except (ValueError, IndexError):
                pass

        return points

    def _parse_arc_path(
        self,
        path_data: str
    ) -> Optional[Tuple[float, float, float, float, float]]:
        try:
            m_match = re.search(r'M\s*([-\d.]+)[,\s]*([-\d.]+)', path_data)
            a_match = re.search(
                r'A\s*([-\d.]+)[,\s]*([-\d.]+)[,\s]*([-\d.]+)[,\s]*(\d)[,\s]*(\d)[,\s]*([-\d.]+)[,\s]*([-\d.]+)',
                path_data
            )

            if m_match and a_match:
                x1 = parse_float(m_match.group(1)) * self.SCALE
                y1 = parse_float(m_match.group(2)) * self.SCALE
                rx = parse_float(a_match.group(1)) * self.SCALE
                ry = parse_float(a_match.group(2)) * self.SCALE
                x2 = parse_float(a_match.group(6)) * self.SCALE
                y2 = parse_float(a_match.group(7)) * self.SCALE

                radius = (rx + ry) / 2

                cx = (x1 + x2) / 2
                cy = (y1 + y2) / 2

                start_angle = math.degrees(math.atan2(y1 - cy, x1 - cx))
                end_angle = math.degrees(math.atan2(y2 - cy, x2 - cx))

                return (cx, cy, radius, start_angle, end_angle)

        except Exception:
            pass

        return None

    def _calculate_bounds_and_center(self):
        all_points = []

        for pad in self.current_footprint.pads:
            all_points.append((pad.x, pad.y))

        if not all_points:
            for line in self.current_footprint.lines:
                all_points.extend([(line.x1, line.y1), (line.x2, line.y2)])
            for circle in self.current_footprint.circles:
                all_points.append((circle.cx, circle.cy))

        if not all_points:
            return

        min_x = min(p[0] for p in all_points)
        max_x = max(p[0] for p in all_points)
        min_y = min(p[1] for p in all_points)
        max_y = max(p[1] for p in all_points)

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2

        for pad in self.current_footprint.pads:
            pad.x -= center_x
            pad.y -= center_y

        for line in self.current_footprint.lines:
            line.x1 -= center_x
            line.y1 -= center_y
            line.x2 -= center_x
            line.y2 -= center_y

        for circle in self.current_footprint.circles:
            circle.cx -= center_x
            circle.cy -= center_y

        for arc in self.current_footprint.arcs:
            arc.cx -= center_x
            arc.cy -= center_y

        for polygon in self.current_footprint.polygons:
            for pt in polygon.points:
                pt.x -= center_x
                pt.y -= center_y

        for text in self.current_footprint.texts:
            text.x -= center_x
            text.y -= center_y

        for hole in self.current_footprint.holes:
            hole.x -= center_x
            hole.y -= center_y

    def _calculate_bounds(self):
        all_points = []

        for pad in self.current_footprint.pads:
            hw = pad.width / 2
            hh = pad.height / 2
            all_points.extend([
                (pad.x - hw, pad.y - hh),
                (pad.x + hw, pad.y + hh)
            ])

        for line in self.current_footprint.lines:
            all_points.extend([
                (line.x1, line.y1),
                (line.x2, line.y2)
            ])

        for circle in self.current_footprint.circles:
            all_points.extend([
                (circle.cx - circle.radius, circle.cy - circle.radius),
                (circle.cx + circle.radius, circle.cy + circle.radius)
            ])

        for polygon in self.current_footprint.polygons:
            for pt in polygon.points:
                all_points.append((pt.x, pt.y))

        if all_points:
            self.current_footprint.bounds = bounding_box(all_points)

    def _generate_courtyard(self):
        if not self.current_footprint.bounds:
            return

        bbox = expand_bbox(self.current_footprint.bounds, 0.25)
        min_x, min_y, max_x, max_y = bbox

        courtyard_lines = [
            FootprintLine(min_x, min_y, max_x, min_y, "F.CrtYd", 0.05),
            FootprintLine(max_x, min_y, max_x, max_y, "F.CrtYd", 0.05),
            FootprintLine(max_x, max_y, min_x, max_y, "F.CrtYd", 0.05),
            FootprintLine(min_x, max_y, min_x, min_y, "F.CrtYd", 0.05),
        ]

        self.current_footprint.lines.extend(courtyard_lines)
