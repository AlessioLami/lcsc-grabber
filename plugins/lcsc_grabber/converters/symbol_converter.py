import re
import json
import logging
import math
from typing import Optional, List, Dict, Any, Tuple

from ..api.models import (
    EasyEdaSymbol, SymbolPin, SymbolRectangle, SymbolPolyline,
    SymbolCircle, SymbolArc, SymbolText, Point, PinType, PinShape,
    get_pin_type, guess_reference_prefix
)
from ..utils.geometry import (
    parse_float, parse_int, normalize_angle
)


logger = logging.getLogger(__name__)


class SymbolConverter:

    SCALE = 0.254

    def __init__(self):
        self.current_symbol: Optional[EasyEdaSymbol] = None

    def convert(
        self,
        symbol_data: Dict[str, Any],
        component_name: str = "Component",
        description: str = "",
        category: str = ""
    ) -> Optional[EasyEdaSymbol]:
        try:
            self.current_symbol = EasyEdaSymbol(name=component_name)
            self.current_symbol.prefix = guess_reference_prefix(description, category)

            if isinstance(symbol_data, str):
                try:
                    symbol_data = json.loads(symbol_data)
                except json.JSONDecodeError:
                    logger.error("Failed to parse symbol data as JSON")
                    return None

            shapes = symbol_data.get("shape", [])
            if isinstance(shapes, str):
                shapes = shapes.split("#@$")

            for shape in shapes:
                if isinstance(shape, str):
                    self._parse_shape(shape)

            self._calculate_offset()

            return self.current_symbol

        except Exception as e:
            logger.error(f"Error converting symbol: {e}", exc_info=True)
            return None

    def _parse_shape(self, shape_str: str):
        if not shape_str:
            return

        parts = shape_str.split("~")
        if not parts:
            return

        shape_type = parts[0].upper()

        try:
            if shape_type == "P":
                self._parse_pin(parts, shape_str)
            elif shape_type == "R":
                self._parse_rectangle(parts)
            elif shape_type == "PL":
                self._parse_polyline(parts)
            elif shape_type == "L":
                self._parse_line(parts)
            elif shape_type == "C" or shape_type == "E":
                self._parse_circle(parts)
            elif shape_type == "A":
                self._parse_arc(parts)
            elif shape_type == "T":
                self._parse_text(parts)
            elif shape_type == "PG":
                self._parse_polygon(parts)
        except Exception as e:
            logger.warning(f"Error parsing shape '{shape_type}': {e}")

    def _parse_pin(self, parts: List[str], full_str: str):
        if len(parts) < 7:
            return

        try:
            pin_number = parts[3] if len(parts) > 3 else "?"

            x = parse_float(parts[4]) * self.SCALE
            y = parse_float(parts[5]) * self.SCALE

            rotation = parse_float(parts[6])

            pin_name = ""
            for i in range(10, min(len(parts), 20)):
                part = parts[i]
                if part and not part.startswith("#") and not part.startswith("^^"):
                    if not part.replace(".", "").replace("-", "").isdigit():
                        if part not in ("start", "end", "middle", "show", "hide", "0", "1"):
                            if len(part) > 0 and len(part) < 30:
                                pin_name = part
                                break

            pin_length = 2.54

            kicad_rotation = normalize_angle(rotation + 180)

            pin = SymbolPin(
                number=str(pin_number),
                name=pin_name,
                x=x,
                y=-y,
                length=pin_length,
                rotation=kicad_rotation,
                pin_type=PinType.UNSPECIFIED
            )

            self.current_symbol.pins.append(pin)

        except Exception as e:
            logger.warning(f"Error parsing pin: {e}")

    def _parse_rectangle(self, parts: List[str]):
        if len(parts) < 7:
            return

        try:
            x = parse_float(parts[1]) * self.SCALE
            y = parse_float(parts[2]) * self.SCALE
            width = parse_float(parts[5]) * self.SCALE
            height = parse_float(parts[6]) * self.SCALE

            stroke_width = 0.254
            if len(parts) > 8:
                try:
                    stroke_width = parse_float(parts[8]) * self.SCALE
                except:
                    pass

            rect = SymbolRectangle(
                x=x,
                y=-y - height,
                width=width,
                height=height,
                stroke_width=max(stroke_width, 0.1)
            )

            self.current_symbol.rectangles.append(rect)

        except Exception as e:
            logger.warning(f"Error parsing rectangle: {e}")

    def _parse_polyline(self, parts: List[str]):
        if len(parts) < 2:
            return

        try:
            points_str = parts[1]
            points = self._parse_point_list(points_str)

            if not points:
                return

            stroke_width = 0.254
            if len(parts) > 3:
                try:
                    stroke_width = parse_float(parts[3]) * self.SCALE
                except:
                    pass

            polyline = SymbolPolyline(
                points=points,
                stroke_width=max(stroke_width, 0.1)
            )

            self.current_symbol.polylines.append(polyline)

        except Exception as e:
            logger.warning(f"Error parsing polyline: {e}")

    def _parse_line(self, parts: List[str]):
        if len(parts) < 5:
            return

        try:
            x1 = parse_float(parts[1]) * self.SCALE
            y1 = parse_float(parts[2]) * self.SCALE
            x2 = parse_float(parts[3]) * self.SCALE
            y2 = parse_float(parts[4]) * self.SCALE

            polyline = SymbolPolyline(
                points=[Point(x1, -y1), Point(x2, -y2)],
                stroke_width=0.254
            )

            self.current_symbol.polylines.append(polyline)

        except Exception as e:
            logger.warning(f"Error parsing line: {e}")

    def _parse_circle(self, parts: List[str]):
        if len(parts) < 4:
            return

        try:
            cx = parse_float(parts[1]) * self.SCALE
            cy = parse_float(parts[2]) * self.SCALE
            radius = parse_float(parts[3]) * self.SCALE

            circle = SymbolCircle(
                cx=cx,
                cy=-cy,
                radius=radius,
                stroke_width=0.254
            )

            self.current_symbol.circles.append(circle)

        except Exception as e:
            logger.warning(f"Error parsing circle: {e}")

    def _parse_arc(self, parts: List[str]):
        if len(parts) < 7:
            return

        try:
            cx = parse_float(parts[1]) * self.SCALE
            cy = parse_float(parts[2]) * self.SCALE
            rx = parse_float(parts[3]) * self.SCALE
            ry = parse_float(parts[4]) * self.SCALE
            start_angle = parse_float(parts[5])
            end_angle = parse_float(parts[6])

            radius = (rx + ry) / 2

            arc = SymbolArc(
                cx=cx,
                cy=-cy,
                radius=radius,
                start_angle=-end_angle,
                end_angle=-start_angle,
                stroke_width=0.254
            )

            self.current_symbol.arcs.append(arc)

        except Exception as e:
            logger.warning(f"Error parsing arc: {e}")

    def _parse_text(self, parts: List[str]):
        if len(parts) < 7:
            return

        try:
            x = parse_float(parts[2]) * self.SCALE
            y = parse_float(parts[3]) * self.SCALE
            rotation = parse_float(parts[4])
            font_size = parse_float(parts[6]) * self.SCALE if len(parts) > 6 else 1.27

            text_content = parts[8] if len(parts) > 8 else ""

            if text_content and not text_content.startswith("#"):
                text_obj = SymbolText(
                    text=text_content,
                    x=x,
                    y=-y,
                    font_size=max(font_size, 0.5),
                    rotation=rotation
                )
                self.current_symbol.texts.append(text_obj)

        except Exception as e:
            logger.warning(f"Error parsing text: {e}")

    def _parse_polygon(self, parts: List[str]):
        self._parse_polyline(parts)
        if self.current_symbol.polylines:
            self.current_symbol.polylines[-1].fill = "outline"

    def _parse_point_list(self, points_str: str) -> List[Point]:
        points = []
        values = re.split(r'[,\s]+', points_str.strip())

        for i in range(0, len(values) - 1, 2):
            try:
                x = parse_float(values[i]) * self.SCALE
                y = parse_float(values[i + 1]) * self.SCALE
                points.append(Point(x, -y))
            except (ValueError, IndexError):
                pass

        return points

    def _calculate_offset(self):
        all_points = []

        for pin in self.current_symbol.pins:
            all_points.append((pin.x, pin.y))

        for rect in self.current_symbol.rectangles:
            all_points.append((rect.x, rect.y))
            all_points.append((rect.x + rect.width, rect.y + rect.height))

        for poly in self.current_symbol.polylines:
            for pt in poly.points:
                all_points.append((pt.x, pt.y))

        for circle in self.current_symbol.circles:
            all_points.append((circle.cx - circle.radius, circle.cy - circle.radius))
            all_points.append((circle.cx + circle.radius, circle.cy + circle.radius))

        if not all_points:
            return

        min_x = min(p[0] for p in all_points)
        max_x = max(p[0] for p in all_points)
        min_y = min(p[1] for p in all_points)
        max_y = max(p[1] for p in all_points)

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2

        self.current_symbol.offset_x = -center_x
        self.current_symbol.offset_y = -center_y
