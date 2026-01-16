from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum


class PinType(Enum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    PASSIVE = "passive"
    FREE = "free"
    UNSPECIFIED = "unspecified"
    POWER_IN = "power_in"
    POWER_OUT = "power_out"
    OPEN_COLLECTOR = "open_collector"
    OPEN_EMITTER = "open_emitter"
    NO_CONNECT = "no_connect"


class PinShape(Enum):
    LINE = "line"
    INVERTED = "inverted"
    CLOCK = "clock"
    INVERTED_CLOCK = "inverted_clock"
    INPUT_LOW = "input_low"
    CLOCK_LOW = "clock_low"
    OUTPUT_LOW = "output_low"
    EDGE_CLOCK_HIGH = "edge_clock_high"
    NON_LOGIC = "non_logic"


class PadShape(Enum):
    RECT = "rect"
    CIRCLE = "circle"
    OVAL = "oval"
    ROUNDRECT = "roundrect"
    TRAPEZOID = "trapezoid"
    CUSTOM = "custom"


class PadType(Enum):
    SMD = "smd"
    THRU_HOLE = "thru_hole"
    NPTH = "np_thru_hole"
    CONNECT = "connect"


@dataclass
class ComponentInfo:
    lcsc_id: str
    mpn: str = ""
    manufacturer: str = ""
    description: str = ""
    datasheet_url: str = ""
    package: str = ""
    category: str = ""
    stock: int = 0
    price: float = 0.0
    image_url: str = ""

    symbol_data: Optional[Dict] = None
    footprint_data: Optional[Dict] = None
    model_3d_uuid: Optional[str] = None

    def has_symbol(self) -> bool:
        return self.symbol_data is not None

    def has_footprint(self) -> bool:
        return self.footprint_data is not None

    def has_3d_model(self) -> bool:
        return self.model_3d_uuid is not None


@dataclass
class Point:
    x: float
    y: float


@dataclass
class SymbolPin:
    number: str
    name: str
    x: float
    y: float
    length: float
    rotation: float
    pin_type: PinType = PinType.UNSPECIFIED
    pin_shape: PinShape = PinShape.LINE
    hidden: bool = False
    name_visible: bool = True
    number_visible: bool = True


@dataclass
class SymbolRectangle:
    x: float
    y: float
    width: float
    height: float
    stroke_width: float = 0.254
    fill: str = "none"


@dataclass
class SymbolPolyline:
    points: List[Point] = field(default_factory=list)
    stroke_width: float = 0.254
    fill: str = "none"


@dataclass
class SymbolCircle:
    cx: float
    cy: float
    radius: float
    stroke_width: float = 0.254
    fill: str = "none"


@dataclass
class SymbolArc:
    cx: float
    cy: float
    radius: float
    start_angle: float
    end_angle: float
    stroke_width: float = 0.254


@dataclass
class SymbolText:
    text: str
    x: float
    y: float
    font_size: float = 1.27
    rotation: float = 0
    h_align: str = "center"
    v_align: str = "center"


@dataclass
class EasyEdaSymbol:
    name: str
    prefix: str = "U"

    pins: List[SymbolPin] = field(default_factory=list)
    rectangles: List[SymbolRectangle] = field(default_factory=list)
    polylines: List[SymbolPolyline] = field(default_factory=list)
    circles: List[SymbolCircle] = field(default_factory=list)
    arcs: List[SymbolArc] = field(default_factory=list)
    texts: List[SymbolText] = field(default_factory=list)

    properties: Dict[str, str] = field(default_factory=dict)

    offset_x: float = 0
    offset_y: float = 0

    unit_count: int = 1


@dataclass
class FootprintPad:
    number: str
    x: float
    y: float
    width: float
    height: float
    shape: PadShape = PadShape.RECT
    pad_type: PadType = PadType.SMD
    rotation: float = 0
    drill_size: float = 0
    drill_shape: str = "circle"
    layers: List[str] = field(default_factory=lambda: ["F.Cu", "F.Paste", "F.Mask"])
    roundrect_ratio: float = 0.25


@dataclass
class FootprintLine:
    x1: float
    y1: float
    x2: float
    y2: float
    layer: str
    stroke_width: float = 0.12


@dataclass
class FootprintCircle:
    cx: float
    cy: float
    radius: float
    layer: str
    stroke_width: float = 0.12
    fill: str = "none"


@dataclass
class FootprintArc:
    cx: float
    cy: float
    radius: float
    start_angle: float
    end_angle: float
    layer: str
    stroke_width: float = 0.12


@dataclass
class FootprintPolygon:
    points: List[Point] = field(default_factory=list)
    layer: str = "F.SilkS"
    stroke_width: float = 0.12
    fill: str = "solid"


@dataclass
class FootprintText:
    text: str
    x: float
    y: float
    layer: str
    font_size: float = 1.0
    thickness: float = 0.15
    rotation: float = 0
    text_type: str = "user"


@dataclass
class FootprintHole:
    x: float
    y: float
    diameter: float


@dataclass
class EasyEdaFootprint:
    name: str

    pads: List[FootprintPad] = field(default_factory=list)
    lines: List[FootprintLine] = field(default_factory=list)
    circles: List[FootprintCircle] = field(default_factory=list)
    arcs: List[FootprintArc] = field(default_factory=list)
    polygons: List[FootprintPolygon] = field(default_factory=list)
    texts: List[FootprintText] = field(default_factory=list)
    holes: List[FootprintHole] = field(default_factory=list)

    model_3d_path: Optional[str] = None
    model_3d_offset: Tuple[float, float, float] = (0, 0, 0)
    model_3d_rotation: Tuple[float, float, float] = (0, 0, 0)
    model_3d_scale: Tuple[float, float, float] = (1, 1, 1)

    bounds: Optional[Tuple[float, float, float, float]] = None

    def has_courtyard(self) -> bool:
        return any(
            line.layer == "F.CrtYd" or line.layer == "B.CrtYd"
            for line in self.lines
        )


@dataclass
class Model3D:
    uuid: str
    step_data: Optional[bytes] = None
    obj_data: Optional[str] = None
    wrl_data: Optional[str] = None
    file_path: Optional[str] = None


EASYEDA_LAYER_MAP = {
    "1": "F.Cu",
    "2": "B.Cu",
    "3": "F.SilkS",
    "4": "B.SilkS",
    "5": "F.Paste",
    "6": "B.Paste",
    "7": "F.Mask",
    "8": "B.Mask",
    "10": "Edge.Cuts",
    "11": "Edge.Cuts",
    "12": "Cmts.User",
    "13": "F.Fab",
    "14": "B.Fab",
    "15": "Dwgs.User",
    "21": "F.CrtYd",
    "22": "B.CrtYd",
    "99": "F.Fab",
    "100": "F.SilkS",
    "101": "F.SilkS",
}


def get_kicad_layer(easyeda_layer: str) -> str:
    return EASYEDA_LAYER_MAP.get(str(easyeda_layer), "F.SilkS")


EASYEDA_PIN_TYPE_MAP = {
    "0": PinType.UNSPECIFIED,
    "1": PinType.INPUT,
    "2": PinType.OUTPUT,
    "3": PinType.BIDIRECTIONAL,
    "4": PinType.POWER_IN,
    "5": PinType.POWER_OUT,
    "6": PinType.OPEN_COLLECTOR,
    "7": PinType.OPEN_EMITTER,
    "8": PinType.PASSIVE,
    "9": PinType.TRI_STATE,
    "10": PinType.NO_CONNECT,
}


def get_pin_type(easyeda_pin_type: str) -> PinType:
    return EASYEDA_PIN_TYPE_MAP.get(str(easyeda_pin_type), PinType.UNSPECIFIED)


COMPONENT_PREFIX_MAP = {
    "resistor": "R",
    "capacitor": "C",
    "inductor": "L",
    "diode": "D",
    "led": "D",
    "transistor": "Q",
    "mosfet": "Q",
    "ic": "U",
    "mcu": "U",
    "microcontroller": "U",
    "connector": "J",
    "switch": "SW",
    "relay": "K",
    "crystal": "Y",
    "oscillator": "Y",
    "transformer": "T",
    "fuse": "F",
    "sensor": "U",
}


def guess_reference_prefix(description: str, category: str) -> str:
    search_text = (description + " " + category).lower()

    for keyword, prefix in COMPONENT_PREFIX_MAP.items():
        if keyword in search_text:
            return prefix

    return "U"
