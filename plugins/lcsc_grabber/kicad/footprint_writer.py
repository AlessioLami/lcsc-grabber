import logging
import math
from pathlib import Path
from typing import Optional, List, Tuple

from ..api.models import (
    EasyEdaFootprint, FootprintPad, FootprintLine, FootprintCircle,
    FootprintArc, FootprintPolygon, FootprintText, FootprintHole,
    PadShape, PadType
)
from ..utils.geometry import format_mm, round_to_grid


logger = logging.getLogger(__name__)


class FootprintWriter:

    VERSION = "20231120"
    GENERATOR = "lcsc_grabber"

    def __init__(self):
        self._indent = 0

    def _fmt(self, value: float) -> str:
        return format_mm(round_to_grid(value, 0.001), precision=6)

    def _line(self, content: str) -> str:
        return "  " * self._indent + content

    def _escape_string(self, s: str) -> str:
        if not s:
            return '""'
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'

    def write_footprint(
        self,
        footprint: EasyEdaFootprint,
        model_path: Optional[str] = None,
        model_offset: Tuple[float, float, float] = (0, 0, 0),
        model_rotation: Tuple[float, float, float] = (0, 0, 0),
        model_scale: Tuple[float, float, float] = (1, 1, 1)
    ) -> str:
        lines = []
        self._indent = 0

        fp_name = self._sanitize_name(footprint.name)

        lines.append(f'(footprint {self._escape_string(fp_name)}')
        self._indent += 1

        lines.append(self._line(f'(version {self.VERSION})'))
        lines.append(self._line(f'(generator "{self.GENERATOR}")'))
        lines.append(self._line(f'(generator_version "1.0")'))
        lines.append(self._line('(layer "F.Cu")'))

        lines.extend(self._write_properties(footprint))

        lines.append(self._line('(attr smd)'))

        lines.extend(self._write_lines(footprint))
        lines.extend(self._write_circles(footprint))
        lines.extend(self._write_arcs(footprint))
        lines.extend(self._write_polygons(footprint))
        lines.extend(self._write_texts(footprint))

        lines.extend(self._write_pads(footprint))

        lines.extend(self._write_holes(footprint))

        if model_path:
            lines.extend(self._write_3d_model(
                model_path, model_offset, model_rotation, model_scale
            ))

        self._indent -= 1
        lines.append(")")

        return "\n".join(lines)

    def _write_properties(self, footprint: EasyEdaFootprint) -> List[str]:
        lines = []

        lines.append(self._line('(property "Reference" "REF**"'))
        self._indent += 1
        lines.append(self._line('(at 0 -2 0)'))
        lines.append(self._line('(layer "F.SilkS")'))
        lines.append(self._line('(uuid "00000000-0000-0000-0000-000000000001")'))
        lines.append(self._line('(effects (font (size 1 1) (thickness 0.15)))'))
        self._indent -= 1
        lines.append(self._line(')'))

        lines.append(self._line(f'(property "Value" {self._escape_string(footprint.name)}'))
        self._indent += 1
        lines.append(self._line('(at 0 2 0)'))
        lines.append(self._line('(layer "F.Fab")'))
        lines.append(self._line('(uuid "00000000-0000-0000-0000-000000000002")'))
        lines.append(self._line('(effects (font (size 1 1) (thickness 0.15)))'))
        self._indent -= 1
        lines.append(self._line(')'))

        return lines

    def _write_lines(self, footprint: EasyEdaFootprint) -> List[str]:
        lines = []

        for line in footprint.lines:
            lines.append(self._line('(fp_line'))
            self._indent += 1
            lines.append(self._line(
                f'(start {self._fmt(line.x1)} {self._fmt(line.y1)})'
            ))
            lines.append(self._line(
                f'(end {self._fmt(line.x2)} {self._fmt(line.y2)})'
            ))
            lines.append(self._line(
                f'(stroke (width {self._fmt(line.stroke_width)}) (type solid))'
            ))
            lines.append(self._line(f'(layer "{line.layer}")'))
            self._indent -= 1
            lines.append(self._line(')'))

        return lines

    def _write_circles(self, footprint: EasyEdaFootprint) -> List[str]:
        lines = []

        for circle in footprint.circles:
            end_x = circle.cx + circle.radius
            end_y = circle.cy

            lines.append(self._line('(fp_circle'))
            self._indent += 1
            lines.append(self._line(
                f'(center {self._fmt(circle.cx)} {self._fmt(circle.cy)})'
            ))
            lines.append(self._line(
                f'(end {self._fmt(end_x)} {self._fmt(end_y)})'
            ))
            lines.append(self._line(
                f'(stroke (width {self._fmt(circle.stroke_width)}) (type solid))'
            ))
            lines.append(self._line(f'(fill {circle.fill})'))
            lines.append(self._line(f'(layer "{circle.layer}")'))
            self._indent -= 1
            lines.append(self._line(')'))

        return lines

    def _write_arcs(self, footprint: EasyEdaFootprint) -> List[str]:
        lines = []

        for arc in footprint.arcs:
            start_rad = math.radians(arc.start_angle)
            end_rad = math.radians(arc.end_angle)
            mid_angle = (arc.start_angle + arc.end_angle) / 2
            mid_rad = math.radians(mid_angle)

            start_x = arc.cx + arc.radius * math.cos(start_rad)
            start_y = arc.cy + arc.radius * math.sin(start_rad)
            mid_x = arc.cx + arc.radius * math.cos(mid_rad)
            mid_y = arc.cy + arc.radius * math.sin(mid_rad)
            end_x = arc.cx + arc.radius * math.cos(end_rad)
            end_y = arc.cy + arc.radius * math.sin(end_rad)

            lines.append(self._line('(fp_arc'))
            self._indent += 1
            lines.append(self._line(
                f'(start {self._fmt(start_x)} {self._fmt(start_y)})'
            ))
            lines.append(self._line(
                f'(mid {self._fmt(mid_x)} {self._fmt(mid_y)})'
            ))
            lines.append(self._line(
                f'(end {self._fmt(end_x)} {self._fmt(end_y)})'
            ))
            lines.append(self._line(
                f'(stroke (width {self._fmt(arc.stroke_width)}) (type solid))'
            ))
            lines.append(self._line(f'(layer "{arc.layer}")'))
            self._indent -= 1
            lines.append(self._line(')'))

        return lines

    def _write_polygons(self, footprint: EasyEdaFootprint) -> List[str]:
        lines = []

        for polygon in footprint.polygons:
            if len(polygon.points) < 3:
                continue

            lines.append(self._line('(fp_poly'))
            self._indent += 1

            lines.append(self._line('(pts'))
            self._indent += 1
            for pt in polygon.points:
                lines.append(self._line(
                    f'(xy {self._fmt(pt.x)} {self._fmt(pt.y)})'
                ))
            self._indent -= 1
            lines.append(self._line(')'))

            lines.append(self._line(
                f'(stroke (width {self._fmt(polygon.stroke_width)}) (type solid))'
            ))
            lines.append(self._line(f'(fill {polygon.fill})'))
            lines.append(self._line(f'(layer "{polygon.layer}")'))

            self._indent -= 1
            lines.append(self._line(')'))

        return lines

    def _write_texts(self, footprint: EasyEdaFootprint) -> List[str]:
        lines = []

        for text in footprint.texts:
            if text.text_type in ("reference", "value"):
                continue

            lines.append(self._line('(fp_text user'))
            self._indent += 1
            lines.append(self._line(self._escape_string(text.text)))
            lines.append(self._line(
                f'(at {self._fmt(text.x)} {self._fmt(text.y)} {int(text.rotation)})'
            ))
            lines.append(self._line(f'(layer "{text.layer}")'))
            lines.append(self._line(
                f'(effects (font (size {self._fmt(text.font_size)} {self._fmt(text.font_size)}) '
                f'(thickness {self._fmt(text.thickness)})))'
            ))
            self._indent -= 1
            lines.append(self._line(')'))

        return lines

    def _write_pads(self, footprint: EasyEdaFootprint) -> List[str]:
        lines = []

        for pad in footprint.pads:
            pad_type = self._get_pad_type_str(pad.pad_type)
            pad_shape = self._get_pad_shape_str(pad.shape)

            lines.append(self._line(
                f'(pad {self._escape_string(pad.number)} {pad_type} {pad_shape}'
            ))
            self._indent += 1

            if pad.rotation != 0:
                lines.append(self._line(
                    f'(at {self._fmt(pad.x)} {self._fmt(pad.y)} {self._fmt(pad.rotation)})'
                ))
            else:
                lines.append(self._line(
                    f'(at {self._fmt(pad.x)} {self._fmt(pad.y)})'
                ))

            lines.append(self._line(
                f'(size {self._fmt(pad.width)} {self._fmt(pad.height)})'
            ))

            if pad.pad_type == PadType.THRU_HOLE and pad.drill_size > 0:
                lines.append(self._line(
                    f'(drill {self._fmt(pad.drill_size)})'
                ))
            elif pad.pad_type == PadType.NPTH and pad.drill_size > 0:
                lines.append(self._line(
                    f'(drill {self._fmt(pad.drill_size)})'
                ))

            if pad.shape == PadShape.ROUNDRECT:
                lines.append(self._line(
                    f'(roundrect_rratio {self._fmt(pad.roundrect_ratio)})'
                ))

            layers_str = " ".join(f'"{l}"' for l in pad.layers)
            lines.append(self._line(f'(layers {layers_str})'))

            self._indent -= 1
            lines.append(self._line(')'))

        return lines

    def _write_holes(self, footprint: EasyEdaFootprint) -> List[str]:
        lines = []

        for hole in footprint.holes:
            lines.append(self._line('(pad "" np_thru_hole circle'))
            self._indent += 1
            lines.append(self._line(
                f'(at {self._fmt(hole.x)} {self._fmt(hole.y)})'
            ))
            lines.append(self._line(
                f'(size {self._fmt(hole.diameter)} {self._fmt(hole.diameter)})'
            ))
            lines.append(self._line(
                f'(drill {self._fmt(hole.diameter)})'
            ))
            lines.append(self._line('(layers "*.Cu" "*.Mask")'))
            self._indent -= 1
            lines.append(self._line(')'))

        return lines

    def _write_3d_model(
        self,
        model_path: str,
        offset: Tuple[float, float, float],
        rotation: Tuple[float, float, float],
        scale: Tuple[float, float, float]
    ) -> List[str]:
        lines = []

        lines.append(self._line(f'(model {self._escape_string(model_path)}'))
        self._indent += 1

        lines.append(self._line(
            f'(offset (xyz {self._fmt(offset[0])} {self._fmt(offset[1])} {self._fmt(offset[2])}))'
        ))
        lines.append(self._line(
            f'(scale (xyz {self._fmt(scale[0])} {self._fmt(scale[1])} {self._fmt(scale[2])}))'
        ))
        lines.append(self._line(
            f'(rotate (xyz {self._fmt(rotation[0])} {self._fmt(rotation[1])} {self._fmt(rotation[2])}))'
        ))

        self._indent -= 1
        lines.append(self._line(')'))

        return lines

    def _get_pad_type_str(self, pad_type: PadType) -> str:
        type_map = {
            PadType.SMD: "smd",
            PadType.THRU_HOLE: "thru_hole",
            PadType.NPTH: "np_thru_hole",
            PadType.CONNECT: "connect",
        }
        return type_map.get(pad_type, "smd")

    def _get_pad_shape_str(self, shape: PadShape) -> str:
        shape_map = {
            PadShape.RECT: "rect",
            PadShape.CIRCLE: "circle",
            PadShape.OVAL: "oval",
            PadShape.ROUNDRECT: "roundrect",
            PadShape.TRAPEZOID: "trapezoid",
            PadShape.CUSTOM: "custom",
        }
        return shape_map.get(shape, "rect")

    def _sanitize_name(self, name: str) -> str:
        import re
        name = re.sub(r'[^\w\-_.]', '_', name)
        if name and name[0].isdigit():
            name = "_" + name
        return name or "Footprint"

    def save_footprint(
        self,
        footprint: EasyEdaFootprint,
        output_path: str,
        model_path: Optional[str] = None,
        model_offset: Tuple[float, float, float] = (0, 0, 0),
        model_rotation: Tuple[float, float, float] = (0, 0, 0),
        model_scale: Tuple[float, float, float] = (1, 1, 1)
    ):
        content = self.write_footprint(
            footprint,
            model_path=model_path,
            model_offset=model_offset,
            model_rotation=model_rotation,
            model_scale=model_scale
        )
        Path(output_path).write_text(content, encoding="utf-8")
        logger.info(f"Saved footprint: {output_path}")
