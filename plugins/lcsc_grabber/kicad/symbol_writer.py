import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from ..api.models import (
    EasyEdaSymbol, SymbolPin, SymbolRectangle, SymbolPolyline,
    SymbolCircle, SymbolArc, Point, PinType
)
from ..utils.geometry import format_mm, round_to_grid


logger = logging.getLogger(__name__)


class SymbolWriter:

    VERSION = "20231120"
    GENERATOR = "lcsc_grabber"

    def __init__(self):
        self._indent = 0

    def _fmt(self, value: float) -> str:
        return format_mm(round_to_grid(value, 0.01))

    def _line(self, content: str) -> str:
        return "  " * self._indent + content

    def _escape_string(self, s: str) -> str:
        if not s:
            return '""'
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{s}"'

    def write_symbol(
        self,
        symbol: EasyEdaSymbol,
        lcsc_id: str,
        footprint_lib: str = "lcsc_grabber",
        footprint_name: Optional[str] = None,
        datasheet_url: str = "",
        mpn: str = ""
    ) -> str:
        lines = []
        self._indent = 0

        symbol_name = self._sanitize_name(symbol.name or lcsc_id)
        footprint_name = footprint_name or symbol_name

        lines.append(self._line(f'(symbol "{symbol_name}"'))
        self._indent += 1

        lines.extend(self._write_properties(
            symbol, lcsc_id, footprint_lib, footprint_name, datasheet_url, mpn
        ))

        lines.append(self._line(f'(symbol "{symbol_name}_1_1"'))
        self._indent += 1

        lines.extend(self._write_rectangles(symbol))
        lines.extend(self._write_polylines(symbol))
        lines.extend(self._write_circles(symbol))
        lines.extend(self._write_arcs(symbol))
        lines.extend(self._write_pins(symbol))

        self._indent -= 1
        lines.append(self._line(")"))

        self._indent -= 1
        lines.append(self._line(")"))

        return "\n".join(lines)

    def write_library(
        self,
        symbols: List[tuple],
    ) -> str:
        lines = []

        lines.append(f"(kicad_symbol_lib")
        lines.append(f'  (version {self.VERSION})')
        lines.append(f'  (generator "{self.GENERATOR}")')
        lines.append(f'  (generator_version "1.0")')

        for item in symbols:
            if len(item) >= 2:
                symbol, lcsc_id = item[0], item[1]
                footprint_name = item[2] if len(item) > 2 else None
                datasheet = item[3] if len(item) > 3 else ""
                mpn = item[4] if len(item) > 4 else ""

                symbol_content = self.write_symbol(
                    symbol, lcsc_id,
                    footprint_name=footprint_name,
                    datasheet_url=datasheet,
                    mpn=mpn
                )
                lines.append(symbol_content)

        lines.append(")")

        return "\n".join(lines)

    def _write_properties(
        self,
        symbol: EasyEdaSymbol,
        lcsc_id: str,
        footprint_lib: str,
        footprint_name: str,
        datasheet_url: str,
        mpn: str
    ) -> List[str]:
        lines = []
        prop_id = 0

        lines.append(self._line(
            f'(property "Reference" "{symbol.prefix}"'
        ))
        self._indent += 1
        lines.append(self._line(f'(at 0 2.54 0)'))
        lines.append(self._line(self._text_effects()))
        self._indent -= 1
        lines.append(self._line(")"))

        lines.append(self._line(
            f'(property "Value" {self._escape_string(symbol.name)}'
        ))
        self._indent += 1
        lines.append(self._line(f'(at 0 -2.54 0)'))
        lines.append(self._line(self._text_effects()))
        self._indent -= 1
        lines.append(self._line(")"))

        footprint_ref = f"{footprint_lib}:{footprint_name}"
        lines.append(self._line(
            f'(property "Footprint" {self._escape_string(footprint_ref)}'
        ))
        self._indent += 1
        lines.append(self._line(f'(at 0 -5.08 0)'))
        lines.append(self._line(self._text_effects(hide=True)))
        self._indent -= 1
        lines.append(self._line(")"))

        lines.append(self._line(
            f'(property "Datasheet" {self._escape_string(datasheet_url)}'
        ))
        self._indent += 1
        lines.append(self._line(f'(at 0 -7.62 0)'))
        lines.append(self._line(self._text_effects(hide=True)))
        self._indent -= 1
        lines.append(self._line(")"))

        lines.append(self._line(
            f'(property "Description" {self._escape_string(symbol.properties.get("description", ""))}'
        ))
        self._indent += 1
        lines.append(self._line(f'(at 0 -10.16 0)'))
        lines.append(self._line(self._text_effects(hide=True)))
        self._indent -= 1
        lines.append(self._line(")"))

        lines.append(self._line(
            f'(property "LCSC" {self._escape_string(lcsc_id)}'
        ))
        self._indent += 1
        lines.append(self._line(f'(at 0 -12.7 0)'))
        lines.append(self._line(self._text_effects(hide=True)))
        self._indent -= 1
        lines.append(self._line(")"))

        if mpn:
            lines.append(self._line(
                f'(property "MPN" {self._escape_string(mpn)}'
            ))
            self._indent += 1
            lines.append(self._line(f'(at 0 -15.24 0)'))
            lines.append(self._line(self._text_effects(hide=True)))
            self._indent -= 1
            lines.append(self._line(")"))

        if symbol.prefix in ("VCC", "VDD", "GND", "VSS"):
            lines.append(self._line("(power)"))

        lines.append(self._line("(pin_names (offset 1.016))"))
        lines.append(self._line("(exclude_from_sim no)"))
        lines.append(self._line("(in_bom yes)"))
        lines.append(self._line("(on_board yes)"))

        return lines

    def _text_effects(self, hide: bool = False) -> str:
        effects = '(effects (font (size 1.27 1.27))'
        if hide:
            effects += ' hide'
        effects += ')'
        return effects

    def _write_rectangles(self, symbol: EasyEdaSymbol) -> List[str]:
        lines = []

        for rect in symbol.rectangles:
            x = rect.x + symbol.offset_x
            y = rect.y + symbol.offset_y

            lines.append(self._line("(rectangle"))
            self._indent += 1
            lines.append(self._line(
                f"(start {self._fmt(x)} {self._fmt(y)})"
            ))
            lines.append(self._line(
                f"(end {self._fmt(x + rect.width)} {self._fmt(y + rect.height)})"
            ))
            lines.append(self._line(
                f"(stroke (width {self._fmt(rect.stroke_width)}) (type default))"
            ))
            lines.append(self._line(
                f"(fill (type {self._get_fill_type(rect.fill)}))"
            ))
            self._indent -= 1
            lines.append(self._line(")"))

        return lines

    def _write_polylines(self, symbol: EasyEdaSymbol) -> List[str]:
        lines = []

        for poly in symbol.polylines:
            if len(poly.points) < 2:
                continue

            lines.append(self._line("(polyline"))
            self._indent += 1

            lines.append(self._line("(pts"))
            self._indent += 1
            for pt in poly.points:
                x = pt.x + symbol.offset_x
                y = pt.y + symbol.offset_y
                lines.append(self._line(
                    f"(xy {self._fmt(x)} {self._fmt(y)})"
                ))
            self._indent -= 1
            lines.append(self._line(")"))

            lines.append(self._line(
                f"(stroke (width {self._fmt(poly.stroke_width)}) (type default))"
            ))
            lines.append(self._line(
                f"(fill (type {self._get_fill_type(poly.fill)}))"
            ))

            self._indent -= 1
            lines.append(self._line(")"))

        return lines

    def _write_circles(self, symbol: EasyEdaSymbol) -> List[str]:
        lines = []

        for circle in symbol.circles:
            cx = circle.cx + symbol.offset_x
            cy = circle.cy + symbol.offset_y

            lines.append(self._line("(circle"))
            self._indent += 1
            lines.append(self._line(
                f"(center {self._fmt(cx)} {self._fmt(cy)})"
            ))
            lines.append(self._line(
                f"(radius {self._fmt(circle.radius)})"
            ))
            lines.append(self._line(
                f"(stroke (width {self._fmt(circle.stroke_width)}) (type default))"
            ))
            lines.append(self._line(
                f"(fill (type {self._get_fill_type(circle.fill)}))"
            ))
            self._indent -= 1
            lines.append(self._line(")"))

        return lines

    def _write_arcs(self, symbol: EasyEdaSymbol) -> List[str]:
        lines = []

        for arc in symbol.arcs:
            cx = arc.cx + symbol.offset_x
            cy = arc.cy + symbol.offset_y

            import math
            start_rad = math.radians(arc.start_angle)
            end_rad = math.radians(arc.end_angle)

            start_x = cx + arc.radius * math.cos(start_rad)
            start_y = cy + arc.radius * math.sin(start_rad)
            end_x = cx + arc.radius * math.cos(end_rad)
            end_y = cy + arc.radius * math.sin(end_rad)

            mid_angle = (arc.start_angle + arc.end_angle) / 2
            mid_rad = math.radians(mid_angle)
            mid_x = cx + arc.radius * math.cos(mid_rad)
            mid_y = cy + arc.radius * math.sin(mid_rad)

            lines.append(self._line("(arc"))
            self._indent += 1
            lines.append(self._line(
                f"(start {self._fmt(start_x)} {self._fmt(start_y)})"
            ))
            lines.append(self._line(
                f"(mid {self._fmt(mid_x)} {self._fmt(mid_y)})"
            ))
            lines.append(self._line(
                f"(end {self._fmt(end_x)} {self._fmt(end_y)})"
            ))
            lines.append(self._line(
                f"(stroke (width {self._fmt(arc.stroke_width)}) (type default))"
            ))
            lines.append(self._line("(fill (type none))"))
            self._indent -= 1
            lines.append(self._line(")"))

        return lines

    def _write_pins(self, symbol: EasyEdaSymbol) -> List[str]:
        lines = []

        for pin in symbol.pins:
            x = pin.x + symbol.offset_x
            y = pin.y + symbol.offset_y

            pin_type = self._get_pin_type_str(pin.pin_type)
            pin_shape = ""

            lines.append(self._line(
                f"(pin {pin_type} line"
            ))
            self._indent += 1
            lines.append(self._line(
                f"(at {self._fmt(x)} {self._fmt(y)} {int(pin.rotation)})"
            ))
            lines.append(self._line(
                f"(length {self._fmt(pin.length)})"
            ))

            lines.append(self._line(
                f"(name {self._escape_string(pin.name)}"
            ))
            self._indent += 1
            lines.append(self._line("(effects (font (size 1.27 1.27)))"))
            self._indent -= 1
            lines.append(self._line(")"))

            lines.append(self._line(
                f"(number {self._escape_string(pin.number)}"
            ))
            self._indent += 1
            lines.append(self._line("(effects (font (size 1.27 1.27)))"))
            self._indent -= 1
            lines.append(self._line(")"))

            self._indent -= 1
            lines.append(self._line(")"))

        return lines

    def _get_pin_type_str(self, pin_type: PinType) -> str:
        type_map = {
            PinType.INPUT: "input",
            PinType.OUTPUT: "output",
            PinType.BIDIRECTIONAL: "bidirectional",
            PinType.TRI_STATE: "tri_state",
            PinType.PASSIVE: "passive",
            PinType.FREE: "free",
            PinType.UNSPECIFIED: "unspecified",
            PinType.POWER_IN: "power_in",
            PinType.POWER_OUT: "power_out",
            PinType.OPEN_COLLECTOR: "open_collector",
            PinType.OPEN_EMITTER: "open_emitter",
            PinType.NO_CONNECT: "no_connect",
        }
        return type_map.get(pin_type, "unspecified")

    def _get_fill_type(self, fill: str) -> str:
        if fill == "outline":
            return "outline"
        elif fill == "background":
            return "background"
        return "none"

    def _sanitize_name(self, name: str) -> str:
        import re
        name = re.sub(r'[^\w\-_.]', '_', name)
        if name and name[0].isdigit():
            name = "_" + name
        return name or "Component"

    def save_library(
        self,
        symbols: List[tuple],
        output_path: str
    ):
        content = self.write_library(symbols)
        Path(output_path).write_text(content, encoding="utf-8")
        logger.info(f"Saved symbol library: {output_path}")
