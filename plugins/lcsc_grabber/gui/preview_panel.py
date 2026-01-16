import math
import logging
import os
from typing import Optional, List, Tuple

try:
    import wx
except ImportError:
    wx = None

from ..api.models import ComponentInfo, EasyEdaSymbol, EasyEdaFootprint, Point
from ..converters.symbol_converter import SymbolConverter
from ..converters.footprint_converter import FootprintConverter


logger = logging.getLogger(__name__)


class Theme:

    BG_DARKEST = (22, 22, 26)
    BG_BASE = (28, 28, 32)
    BG_ELEVATED = (38, 38, 44)
    BG_HOVER = (50, 50, 58)

    BG_3D_MODEL = (55, 55, 62)

    TEXT_PRIMARY = (210, 210, 215)
    TEXT_SECONDARY = (130, 130, 145)
    TEXT_DISABLED = (80, 80, 92)

    ACCENT = (100, 140, 180)
    ACCENT_HOVER = (120, 160, 200)
    ACCENT_DIM = (80, 110, 140)

    BORDER_SUBTLE = (50, 50, 58)
    BORDER_ACCENT = (80, 110, 140)

    SYMBOL_LINE = (100, 160, 200)
    SYMBOL_PIN = (200, 140, 80)
    SYMBOL_TEXT = (170, 170, 180)

    PAD_COLOR = (200, 160, 80)
    SILK_COLOR = (200, 200, 210)
    COURTYARD_COLOR = (140, 100, 180)
    FAB_COLOR = (100, 100, 110)

    SUCCESS = (90, 160, 90)
    ERROR = (180, 80, 80)

    @staticmethod
    def get_font_primary(size=9, bold=False):
        weight = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
        return wx.Font(size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, weight)

    @staticmethod
    def get_font_accent(size=9, bold=False):
        weight = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
        return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, weight)


class TabButton(wx.Panel if wx else object):

    def __init__(self, parent, label, callback=None):
        super().__init__(parent, style=wx.NO_BORDER)
        self.label = label
        self._callback = callback
        self._selected = False
        self._hover = False

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((90, 28))

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_click)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    def SetCallback(self, callback):
        self._callback = callback

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        if self._selected:
            dc.SetBrush(wx.Brush(wx.Colour(*T.BG_DARKEST)))
            dc.SetPen(wx.TRANSPARENT_PEN)
        elif self._hover:
            dc.SetBrush(wx.Brush(wx.Colour(*T.BG_HOVER)))
            dc.SetPen(wx.TRANSPARENT_PEN)
        else:
            dc.SetBrush(wx.Brush(wx.Colour(*T.BG_ELEVATED)))
            dc.SetPen(wx.TRANSPARENT_PEN)

        dc.DrawRectangle(0, 0, w, h)

        if self._selected:
            dc.SetPen(wx.Pen(wx.Colour(*T.ACCENT), 2))
            dc.DrawLine(4, h - 2, w - 4, h - 2)

        dc.SetFont(T.get_font_accent(9))

        if self._selected:
            dc.SetTextForeground(wx.Colour(*T.TEXT_PRIMARY))
        elif self._hover:
            dc.SetTextForeground(wx.Colour(*T.TEXT_PRIMARY))
        else:
            dc.SetTextForeground(wx.Colour(*T.TEXT_SECONDARY))

        tw, th = dc.GetTextExtent(self.label)
        dc.DrawText(self.label, (w - tw) // 2, (h - th) // 2 - 1)

    def _on_click(self, event):
        if self._callback:
            self._callback()

    def _on_enter(self, event):
        self._hover = True
        self.Refresh()

    def _on_leave(self, event):
        self._hover = False
        self.Refresh()

    def SetSelected(self, selected):
        self._selected = selected
        self.Refresh()


class SymbolPreviewPanel(wx.Panel if wx else object):

    def __init__(self, parent):
        if wx is None:
            raise ImportError("wxPython is not available")

        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(*Theme.BG_DARKEST))

        self.symbol: Optional[EasyEdaSymbol] = None
        self.scale = 10.0
        self.offset_x = 0
        self.offset_y = 0

        self._dragging = False
        self._last_mouse_pos = None

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_scroll)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)

    def set_symbol(self, symbol: EasyEdaSymbol):
        self.symbol = symbol
        self._auto_fit()
        self.Refresh()

    def clear(self):
        self.symbol = None
        self.Refresh()

    def _auto_fit(self):
        if not self.symbol:
            return

        size = self.GetClientSize()
        if size.width <= 0 or size.height <= 0:
            return

        all_x = []
        all_y = []

        for pin in self.symbol.pins:
            px = pin.x + self.symbol.offset_x
            py = pin.y + self.symbol.offset_y
            all_x.append(px)
            all_y.append(py)
            angle = math.radians(pin.rotation)
            ex = px + pin.length * math.cos(angle)
            ey = py + pin.length * math.sin(angle)
            all_x.append(ex)
            all_y.append(ey)

        for rect in self.symbol.rectangles:
            rx = rect.x + self.symbol.offset_x
            ry = rect.y + self.symbol.offset_y
            all_x.extend([rx, rx + rect.width])
            all_y.extend([ry, ry + rect.height])

        for poly in self.symbol.polylines:
            for pt in poly.points:
                all_x.append(pt.x + self.symbol.offset_x)
                all_y.append(pt.y + self.symbol.offset_y)

        for circle in self.symbol.circles:
            cx = circle.cx + self.symbol.offset_x
            cy = circle.cy + self.symbol.offset_y
            all_x.extend([cx - circle.radius, cx + circle.radius])
            all_y.extend([cy - circle.radius, cy + circle.radius])

        if not all_x or not all_y:
            self.offset_x = size.width / 2
            self.offset_y = size.height / 2
            return

        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)

        sym_width = max_x - min_x
        sym_height = max_y - min_y

        if sym_width <= 0:
            sym_width = 10
        if sym_height <= 0:
            sym_height = 10

        margin = 60
        scale_x = (size.width - margin * 2) / sym_width
        scale_y = (size.height - margin * 2) / sym_height
        self.scale = min(scale_x, scale_y, 50.0)
        self.scale = max(self.scale, 1.0)

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        self.offset_x = size.width / 2 - center_x * self.scale
        self.offset_y = size.height / 2 + center_y * self.scale

    def _on_size(self, event):
        if self.symbol:
            self._auto_fit()
        self.Refresh()
        event.Skip()

    def _on_scroll(self, event):
        mouse_pos = event.GetPosition()
        old_scale = self.scale

        if event.GetWheelRotation() > 0:
            self.scale *= 1.2
        else:
            self.scale /= 1.2
        self.scale = max(1.0, min(100.0, self.scale))

        scale_factor = self.scale / old_scale
        self.offset_x = mouse_pos.x - (mouse_pos.x - self.offset_x) * scale_factor
        self.offset_y = mouse_pos.y - (mouse_pos.y - self.offset_y) * scale_factor
        self.Refresh()

    def _on_left_down(self, event):
        self._dragging = True
        self._last_mouse_pos = event.GetPosition()
        self.CaptureMouse()

    def _on_left_up(self, event):
        if self._dragging:
            self._dragging = False
            if self.HasCapture():
                self.ReleaseMouse()

    def _on_motion(self, event):
        if self._dragging and self._last_mouse_pos:
            pos = event.GetPosition()
            dx = pos.x - self._last_mouse_pos.x
            dy = pos.y - self._last_mouse_pos.y
            self.offset_x += dx
            self.offset_y += dy
            self._last_mouse_pos = pos
            self.Refresh()

    def _to_screen(self, x: float, y: float) -> Tuple[int, int]:
        return (
            int(self.offset_x + x * self.scale),
            int(self.offset_y - y * self.scale)
        )

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.Brush(wx.Colour(*T.BG_DARKEST)))
        dc.SetPen(wx.Pen(wx.Colour(*T.BORDER_SUBTLE), 1))
        dc.DrawRectangle(0, 0, w, h)

        if not self.symbol:
            self._draw_empty_state(dc, w, h, "No symbol available", "Search for a component to preview")
            return

        dc.SetPen(wx.Pen(wx.Colour(*T.SYMBOL_LINE), 2))
        dc.SetBrush(wx.TRANSPARENT_BRUSH)

        for rect_shape in self.symbol.rectangles:
            x, y = self._to_screen(
                rect_shape.x + self.symbol.offset_x,
                rect_shape.y + self.symbol.offset_y
            )
            rw = int(rect_shape.width * self.scale)
            rh = int(rect_shape.height * self.scale)
            dc.DrawRectangle(x, y - rh, rw, rh)

        for poly in self.symbol.polylines:
            if len(poly.points) >= 2:
                points = [
                    self._to_screen(
                        pt.x + self.symbol.offset_x,
                        pt.y + self.symbol.offset_y
                    )
                    for pt in poly.points
                ]
                dc.DrawLines([wx.Point(*p) for p in points])

        for circle in self.symbol.circles:
            cx, cy = self._to_screen(
                circle.cx + self.symbol.offset_x,
                circle.cy + self.symbol.offset_y
            )
            r = int(circle.radius * self.scale)
            dc.DrawCircle(cx, cy, r)

        dc.SetPen(wx.Pen(wx.Colour(*T.SYMBOL_PIN), 2))
        dc.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        dc.SetTextForeground(wx.Colour(*T.SYMBOL_TEXT))

        for pin in self.symbol.pins:
            px, py = self._to_screen(
                pin.x + self.symbol.offset_x,
                pin.y + self.symbol.offset_y
            )
            angle = math.radians(pin.rotation)
            length = pin.length * self.scale
            ex = px + int(length * math.cos(angle))
            ey = py - int(length * math.sin(angle))

            dc.DrawLine(px, py, ex, ey)
            dc.DrawCircle(px, py, 3)

            if pin.name and pin.name != pin.number:
                name_text = pin.name[:10]
                tw, th = dc.GetTextExtent(name_text)
                angle_deg = pin.rotation % 360

                if 45 <= angle_deg < 135:
                    text_x, text_y = ex - tw // 2, ey - th - 4
                elif 135 <= angle_deg < 225:
                    text_x, text_y = ex - tw - 4, ey - th // 2
                elif 225 <= angle_deg < 315:
                    text_x, text_y = ex - tw // 2, ey + 4
                else:
                    text_x, text_y = ex + 4, ey - th // 2

                dc.DrawText(name_text, text_x, text_y)

    def _draw_empty_state(self, dc, w, h, title, subtitle):
        T = Theme

        box_w, box_h = 200, 60
        box_x = (w - box_w) // 2
        box_y = (h - box_h) // 2
        dc.SetBrush(wx.Brush(wx.Colour(*T.BG_DARKEST)))
        dc.SetPen(wx.Pen(wx.Colour(*T.BORDER_SUBTLE), 1))
        dc.DrawRectangle(box_x, box_y, box_w, box_h)

        dc.SetFont(T.get_font_accent(10))
        dc.SetTextForeground(wx.Colour(*T.TEXT_SECONDARY))
        tw, th = dc.GetTextExtent(title)
        dc.DrawText(title, (w - tw) // 2, box_y + 12)

        dc.SetFont(T.get_font_primary(9))
        dc.SetTextForeground(wx.Colour(*T.TEXT_DISABLED))
        tw2, th2 = dc.GetTextExtent(subtitle)
        dc.DrawText(subtitle, (w - tw2) // 2, box_y + 34)


class FootprintPreviewPanel(wx.Panel if wx else object):

    def __init__(self, parent):
        if wx is None:
            raise ImportError("wxPython is not available")

        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(*Theme.BG_DARKEST))

        self.footprint: Optional[EasyEdaFootprint] = None
        self.scale = 50.0
        self.offset_x = 0
        self.offset_y = 0

        self._dragging = False
        self._last_mouse_pos = None

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_scroll)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)

    def set_footprint(self, footprint: EasyEdaFootprint):
        self.footprint = footprint
        self._auto_fit()
        self.Refresh()

    def clear(self):
        self.footprint = None
        self.Refresh()

    def _auto_fit(self):
        if not self.footprint:
            return

        size = self.GetClientSize()
        if size.width <= 0 or size.height <= 0:
            return

        all_x = []
        all_y = []

        for pad in self.footprint.pads:
            all_x.extend([pad.x - pad.width/2, pad.x + pad.width/2])
            all_y.extend([pad.y - pad.height/2, pad.y + pad.height/2])

        for line in self.footprint.lines:
            all_x.extend([line.x1, line.x2])
            all_y.extend([line.y1, line.y2])

        for circle in self.footprint.circles:
            all_x.extend([circle.cx - circle.radius, circle.cx + circle.radius])
            all_y.extend([circle.cy - circle.radius, circle.cy + circle.radius])

        if not all_x or not all_y:
            self.offset_x = size.width / 2
            self.offset_y = size.height / 2
            return

        min_x, max_x = min(all_x), max(all_x)
        min_y, max_y = min(all_y), max(all_y)

        fp_width = max_x - min_x
        fp_height = max_y - min_y

        if fp_width <= 0:
            fp_width = 1
        if fp_height <= 0:
            fp_height = 1

        margin = 40
        scale_x = (size.width - margin * 2) / fp_width
        scale_y = (size.height - margin * 2) / fp_height
        self.scale = min(scale_x, scale_y, 500.0)
        self.scale = max(self.scale, 5.0)

        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        self.offset_x = size.width / 2 - center_x * self.scale
        self.offset_y = size.height / 2 + center_y * self.scale

    def _on_size(self, event):
        if self.footprint:
            self._auto_fit()
        self.Refresh()
        event.Skip()

    def _on_scroll(self, event):
        mouse_pos = event.GetPosition()
        old_scale = self.scale

        if event.GetWheelRotation() > 0:
            self.scale *= 1.2
        else:
            self.scale /= 1.2
        self.scale = max(5.0, min(500.0, self.scale))

        scale_factor = self.scale / old_scale
        self.offset_x = mouse_pos.x - (mouse_pos.x - self.offset_x) * scale_factor
        self.offset_y = mouse_pos.y - (mouse_pos.y - self.offset_y) * scale_factor
        self.Refresh()

    def _on_left_down(self, event):
        self._dragging = True
        self._last_mouse_pos = event.GetPosition()
        self.CaptureMouse()

    def _on_left_up(self, event):
        if self._dragging:
            self._dragging = False
            if self.HasCapture():
                self.ReleaseMouse()

    def _on_motion(self, event):
        if self._dragging and self._last_mouse_pos:
            pos = event.GetPosition()
            dx = pos.x - self._last_mouse_pos.x
            dy = pos.y - self._last_mouse_pos.y
            self.offset_x += dx
            self.offset_y += dy
            self._last_mouse_pos = pos
            self.Refresh()

    def _to_screen(self, x: float, y: float) -> Tuple[int, int]:
        return (
            int(self.offset_x + x * self.scale),
            int(self.offset_y - y * self.scale)
        )

    def _get_layer_color(self, layer: str) -> wx.Colour:
        T = Theme
        if "SilkS" in layer:
            return wx.Colour(*T.SILK_COLOR)
        elif "CrtYd" in layer:
            return wx.Colour(*T.COURTYARD_COLOR)
        elif "Fab" in layer:
            return wx.Colour(*T.FAB_COLOR)
        elif "Cu" in layer:
            return wx.Colour(*T.PAD_COLOR)
        return wx.Colour(*T.TEXT_PRIMARY)

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.Brush(wx.Colour(*T.BG_DARKEST)))
        dc.SetPen(wx.Pen(wx.Colour(*T.BORDER_SUBTLE), 1))
        dc.DrawRectangle(0, 0, w, h)

        if not self.footprint:
            self._draw_empty_state(dc, w, h, "No footprint available", "Search for a component to preview")
            return

        for line in self.footprint.lines:
            color = self._get_layer_color(line.layer)
            dc.SetPen(wx.Pen(color, max(1, int(line.stroke_width * self.scale))))
            x1, y1 = self._to_screen(line.x1, line.y1)
            x2, y2 = self._to_screen(line.x2, line.y2)
            dc.DrawLine(x1, y1, x2, y2)

        for circle in self.footprint.circles:
            color = self._get_layer_color(circle.layer)
            dc.SetPen(wx.Pen(color, max(1, int(circle.stroke_width * self.scale))))
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            cx, cy = self._to_screen(circle.cx, circle.cy)
            r = int(circle.radius * self.scale)
            dc.DrawCircle(cx, cy, r)

        pad_color = wx.Colour(*T.PAD_COLOR)
        dc.SetPen(wx.Pen(pad_color, 1))
        dc.SetBrush(wx.Brush(pad_color))
        dc.SetFont(wx.Font(7, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))

        for pad in self.footprint.pads:
            px, py = self._to_screen(pad.x, pad.y)
            pw = int(pad.width * self.scale)
            ph = int(pad.height * self.scale)
            pw = max(pw, 2)
            ph = max(ph, 2)

            dc.DrawRectangle(px - pw // 2, py - ph // 2, pw, ph)

            if pw > 15 and ph > 12:
                dc.SetTextForeground(wx.Colour(*T.BG_DARKEST))
                num_str = str(pad.number)
                tw, th = dc.GetTextExtent(num_str)
                if tw < pw - 2 and th < ph - 2:
                    dc.DrawText(num_str, px - tw // 2, py - th // 2)

    def _draw_empty_state(self, dc, w, h, title, subtitle):
        T = Theme

        box_w, box_h = 200, 60
        box_x = (w - box_w) // 2
        box_y = (h - box_h) // 2
        dc.SetBrush(wx.Brush(wx.Colour(*T.BG_DARKEST)))
        dc.SetPen(wx.Pen(wx.Colour(*T.BORDER_SUBTLE), 1))
        dc.DrawRectangle(box_x, box_y, box_w, box_h)

        dc.SetFont(T.get_font_accent(10))
        dc.SetTextForeground(wx.Colour(*T.TEXT_SECONDARY))
        tw, th = dc.GetTextExtent(title)
        dc.DrawText(title, (w - tw) // 2, box_y + 12)

        dc.SetFont(T.get_font_primary(9))
        dc.SetTextForeground(wx.Colour(*T.TEXT_DISABLED))
        tw2, th2 = dc.GetTextExtent(subtitle)
        dc.DrawText(subtitle, (w - tw2) // 2, box_y + 34)


class Model3DPreviewPanel(wx.Panel if wx else object):

    BG_COLOR = (Theme.BG_3D_MODEL[0]/255, Theme.BG_3D_MODEL[1]/255, Theme.BG_3D_MODEL[2]/255)

    def __init__(self, parent):
        if wx is None:
            raise ImportError("wxPython is not available")

        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(*Theme.BG_3D_MODEL))

        self.model_uuid: Optional[str] = None
        self.lcsc_id: Optional[str] = None
        self._component_loaded = False
        self._gl_canvas = None
        self._gl_context = None
        self._vertices = []
        self._faces = []
        self._gl_initialized = False
        self._z_range = (0, 1)

        self._rot_x = 25.0
        self._rot_z = -45.0
        self._zoom = 1.0

        self._dragging = False
        self._last_mouse_pos = None

        self._init_gl()

    def _init_gl(self):
        try:
            from wx import glcanvas
            from OpenGL import GL
            self._GL = GL

            attribs = [
                glcanvas.WX_GL_RGBA,
                glcanvas.WX_GL_DOUBLEBUFFER,
                glcanvas.WX_GL_DEPTH_SIZE, 24,
                glcanvas.WX_GL_SAMPLE_BUFFERS, 1,
                glcanvas.WX_GL_SAMPLES, 4,
                0
            ]

            self._gl_canvas = glcanvas.GLCanvas(self, attribList=attribs)
            self._gl_context = glcanvas.GLContext(self._gl_canvas)

            sizer = wx.BoxSizer(wx.VERTICAL)
            sizer.Add(self._gl_canvas, 1, wx.EXPAND)
            self.SetSizer(sizer)

            self._gl_canvas.Bind(wx.EVT_PAINT, self._on_paint_gl)
            self._gl_canvas.Bind(wx.EVT_SIZE, self._on_size_gl)
            self._gl_canvas.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_down)
            self._gl_canvas.Bind(wx.EVT_LEFT_UP, self._on_mouse_up)
            self._gl_canvas.Bind(wx.EVT_MOTION, self._on_mouse_motion)
            self._gl_canvas.Bind(wx.EVT_MOUSEWHEEL, self._on_mouse_wheel)
            self._gl_canvas.Bind(wx.EVT_LEFT_DCLICK, self._on_reset_view)

        except ImportError as e:
            logger.warning(f"OpenGL not available: {e}")
            self._gl_canvas = None
            self.Bind(wx.EVT_PAINT, self._on_paint_fallback)

    def set_model(self, model_uuid: Optional[str], lcsc_id: str, model_path: Optional[str] = None):
        self.model_uuid = model_uuid
        self.lcsc_id = lcsc_id
        self._component_loaded = True
        self._vertices = []
        self._faces = []

        self._rot_x = 25.0
        self._rot_z = -45.0
        self._zoom = 1.0

        if model_uuid:
            self._load_model()

        if self._gl_canvas:
            self._gl_canvas.Refresh()
        else:
            self.Refresh()

    def _load_model(self):
        if not self.model_uuid or not self.lcsc_id:
            return

        try:
            from ..api.easyeda_client import get_client
            client = get_client()
            obj_data = client.get_3d_model_obj(self.model_uuid)
            if obj_data:
                self._parse_obj(obj_data)
        except Exception as e:
            logger.error(f"Error loading 3D model: {e}")

    def _parse_obj(self, obj_data: str):
        vertices = []
        faces = []
        current_mtl = "default"

        for line in obj_data.splitlines():
            line = line.strip()
            if line.startswith("v "):
                parts = line.split()
                if len(parts) >= 4:
                    try:
                        vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                    except ValueError:
                        pass
            elif line.startswith("usemtl "):
                current_mtl = line[7:].strip().lower()
            elif line.startswith("f "):
                indices = []
                for p in line.split()[1:]:
                    try:
                        idx = int(p.split("/")[0]) - 1
                        if 0 <= idx < len(vertices):
                            indices.append(idx)
                    except (ValueError, IndexError):
                        pass
                if len(indices) >= 3:
                    for i in range(1, len(indices) - 1):
                        faces.append(([indices[0], indices[i], indices[i+1]], current_mtl))

        if not vertices or not faces:
            return

        min_v = [min(v[i] for v in vertices) for i in range(3)]
        max_v = [max(v[i] for v in vertices) for i in range(3)]
        center = [(min_v[i] + max_v[i]) / 2 for i in range(3)]
        max_dim = max(max_v[i] - min_v[i] for i in range(3))
        scale = 2.0 / max(max_dim, 0.001)

        self._vertices = [
            [(v[0] - center[0]) * scale, (v[1] - center[1]) * scale, (v[2] - center[2]) * scale]
            for v in vertices
        ]

        seen_faces = set()
        unique_faces = []
        for indices, mtl in faces:
            key = tuple(sorted(indices))
            if key not in seen_faces:
                seen_faces.add(key)
                unique_faces.append((indices, mtl))

        self._faces = unique_faces
        self._z_range = ((min_v[2] - center[2]) * scale, (max_v[2] - center[2]) * scale)

    def _get_color_gl(self, mtl: str, z_pos: float) -> Tuple[float, float, float]:
        mtl_lower = mtl.lower()

        if 'pin' in mtl_lower or 'lead' in mtl_lower or 'metal' in mtl_lower or 'terminal' in mtl_lower:
            return (0.75, 0.75, 0.78)
        elif 'gold' in mtl_lower:
            return (0.85, 0.65, 0.13)
        elif 'pad' in mtl_lower or 'solder' in mtl_lower:
            return (0.7, 0.7, 0.72)
        elif 'mark' in mtl_lower or 'label' in mtl_lower or 'text' in mtl_lower:
            return (0.9, 0.9, 0.9)
        else:
            z_range = self._z_range[1] - self._z_range[0]
            if z_range > 0:
                z_ratio = (z_pos - self._z_range[0]) / z_range
            else:
                z_ratio = 0.5

            if z_ratio > 0.7:
                return (0.18, 0.18, 0.20)
            elif z_ratio < 0.3:
                return (0.12, 0.12, 0.14)
            else:
                return (0.15, 0.15, 0.17)

    def _setup_gl(self):
        GL = self._GL

        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glClearDepth(1.0)
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glLightModeli(GL.GL_LIGHT_MODEL_TWO_SIDE, GL.GL_TRUE)
        GL.glShadeModel(GL.GL_SMOOTH)
        GL.glEnable(GL.GL_NORMALIZE)

        GL.glEnable(GL.GL_LIGHTING)
        GL.glEnable(GL.GL_LIGHT0)

        GL.glLightModelfv(GL.GL_LIGHT_MODEL_AMBIENT, [0.2, 0.2, 0.2, 1.0])

        GL.glLightfv(GL.GL_LIGHT0, GL.GL_POSITION, [0.3, 0.5, 1.0, 0.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_AMBIENT, [0.0, 0.0, 0.0, 1.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_DIFFUSE, [0.6, 0.6, 0.6, 1.0])
        GL.glLightfv(GL.GL_LIGHT0, GL.GL_SPECULAR, [0.0, 0.0, 0.0, 1.0])

        GL.glEnable(GL.GL_COLOR_MATERIAL)
        GL.glColorMaterial(GL.GL_FRONT_AND_BACK, GL.GL_AMBIENT_AND_DIFFUSE)

        GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        GL.glPolygonOffset(2.0, 2.0)
        GL.glEnable(GL.GL_MULTISAMPLE)

        self._gl_initialized = True

    def _on_mouse_down(self, event):
        self._dragging = True
        self._last_mouse_pos = event.GetPosition()
        self._gl_canvas.CaptureMouse()

    def _on_mouse_up(self, event):
        self._dragging = False
        self._last_mouse_pos = None
        if self._gl_canvas.HasCapture():
            self._gl_canvas.ReleaseMouse()

    def _on_mouse_motion(self, event):
        if not self._dragging or not self._last_mouse_pos:
            return

        pos = event.GetPosition()
        dx = pos.x - self._last_mouse_pos.x
        dy = pos.y - self._last_mouse_pos.y

        self._rot_z -= dx * 0.5
        self._rot_x += dy * 0.5

        self._last_mouse_pos = pos
        self._gl_canvas.Refresh()

    def _on_mouse_wheel(self, event):
        rotation = event.GetWheelRotation()
        if rotation > 0:
            self._zoom *= 1.1
        else:
            self._zoom /= 1.1
        self._zoom = max(0.2, min(5.0, self._zoom))
        self._gl_canvas.Refresh()

    def _on_reset_view(self, event):
        self._rot_x = 25.0
        self._rot_z = -45.0
        self._zoom = 1.0
        self._gl_canvas.Refresh()

    def _on_paint_gl(self, event):
        if not self._gl_canvas or not self._gl_context:
            return

        self._gl_canvas.SetCurrent(self._gl_context)
        GL = self._GL

        if not self._gl_initialized:
            self._setup_gl()

        w, h = self._gl_canvas.GetClientSize()
        GL.glViewport(0, 0, w, h)

        GL.glClearColor(*self.BG_COLOR, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)

        if not self._vertices:
            self._gl_canvas.SwapBuffers()
            return

        GL.glMatrixMode(GL.GL_PROJECTION)
        GL.glLoadIdentity()
        aspect = w / max(h, 1)
        z = 1.5 / self._zoom
        GL.glOrtho(-aspect * z, aspect * z, -z, z, -5, 5)

        GL.glMatrixMode(GL.GL_MODELVIEW)
        GL.glLoadIdentity()
        GL.glRotatef(self._rot_x, 1, 0, 0)
        GL.glRotatef(self._rot_z, 0, 1, 0)

        GL.glBegin(GL.GL_TRIANGLES)
        for indices, mtl in self._faces:
            v0, v1, v2 = [self._vertices[i] for i in indices]

            e1 = [v1[i] - v0[i] for i in range(3)]
            e2 = [v2[i] - v0[i] for i in range(3)]
            nx = e1[1]*e2[2] - e1[2]*e2[1]
            ny = e1[2]*e2[0] - e1[0]*e2[2]
            nz = e1[0]*e2[1] - e1[1]*e2[0]
            nl = math.sqrt(nx*nx + ny*ny + nz*nz)
            if nl > 0.0001:
                nx, ny, nz = nx/nl, ny/nl, nz/nl
            else:
                nx, ny, nz = 0, 0, 1

            avg_z = (v0[2] + v1[2] + v2[2]) / 3
            color = self._get_color_gl(mtl, avg_z)

            GL.glNormal3f(nx, ny, nz)
            GL.glColor3f(*color)
            GL.glVertex3f(*v0)
            GL.glVertex3f(*v1)
            GL.glVertex3f(*v2)

        GL.glEnd()
        self._gl_canvas.SwapBuffers()

    def _on_size_gl(self, event):
        if self._gl_canvas:
            self._gl_canvas.Refresh()
        event.Skip()

    def _on_paint_fallback(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.Brush(wx.Colour(*T.BG_3D_MODEL)))
        dc.SetPen(wx.Pen(wx.Colour(*T.BORDER_SUBTLE), 1))
        dc.DrawRectangle(0, 0, w, h)

        if not self._component_loaded:
            title = "No component selected"
            subtitle = "Search for a part number"
        elif not self.model_uuid:
            title = "No 3D model"
            subtitle = "Component has no 3D model data"
        else:
            title = "OpenGL unavailable"
            subtitle = "Install PyOpenGL for 3D preview"

        box_w, box_h = 200, 60
        box_x = (w - box_w) // 2
        box_y = (h - box_h) // 2
        dc.SetBrush(wx.Brush(wx.Colour(*T.BG_3D_MODEL)))
        dc.SetPen(wx.Pen(wx.Colour(*T.BORDER_SUBTLE), 1))
        dc.DrawRectangle(box_x, box_y, box_w, box_h)

        dc.SetFont(T.get_font_accent(10))
        dc.SetTextForeground(wx.Colour(*T.TEXT_SECONDARY))
        tw, th = dc.GetTextExtent(title)
        dc.DrawText(title, (w - tw) // 2, box_y + 12)

        dc.SetFont(T.get_font_primary(9))
        dc.SetTextForeground(wx.Colour(*T.TEXT_DISABLED))
        tw2, th2 = dc.GetTextExtent(subtitle)
        dc.DrawText(subtitle, (w - tw2) // 2, box_y + 34)

    def clear(self):
        self.model_uuid = None
        self.lcsc_id = None
        self._component_loaded = False
        self._vertices = []
        self._faces = []
        if self._gl_canvas:
            self._gl_canvas.Refresh()
        else:
            self.Refresh()


class DataInfoPanel(wx.Panel):

    def __init__(self, parent):
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(*Theme.BG_DARKEST))

        self._lines = []
        self._scroll_y = 0
        self._line_height = 18
        self._component_loaded = False

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_scroll)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def set_info(self, text: str):
        self._lines = text.split('\n') if text else []
        self._scroll_y = 0
        self._component_loaded = True
        self.Refresh()

    def clear(self):
        self._lines = []
        self._scroll_y = 0
        self._component_loaded = False
        self.Refresh()

    def _on_size(self, event):
        self.Refresh()
        event.Skip()

    def _on_scroll(self, event):
        rotation = event.GetWheelRotation()
        if rotation > 0:
            self._scroll_y = max(0, self._scroll_y - 3)
        else:
            max_scroll = max(0, len(self._lines) - (self.GetClientSize().height // self._line_height) + 2)
            self._scroll_y = min(max_scroll, self._scroll_y + 3)
        self.Refresh()

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.Brush(wx.Colour(*T.BG_DARKEST)))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, w, h)

        if not self._component_loaded:
            box_w, box_h = 200, 60
            box_x = (w - box_w) // 2
            box_y = (h - box_h) // 2
            dc.SetBrush(wx.Brush(wx.Colour(*T.BG_DARKEST)))
            dc.SetPen(wx.Pen(wx.Colour(*T.BORDER_SUBTLE), 1))
            dc.DrawRectangle(box_x, box_y, box_w, box_h)

            dc.SetFont(T.get_font_accent(10))
            dc.SetTextForeground(wx.Colour(*T.TEXT_SECONDARY))
            title = "No component selected"
            tw, th = dc.GetTextExtent(title)
            dc.DrawText(title, (w - tw) // 2, box_y + 12)

            dc.SetFont(T.get_font_primary(9))
            dc.SetTextForeground(wx.Colour(*T.TEXT_DISABLED))
            hint = "Search for a part number"
            tw2, th2 = dc.GetTextExtent(hint)
            dc.DrawText(hint, (w - tw2) // 2, box_y + 34)
            return

        dc.SetFont(T.get_font_primary(9))
        margin = 12
        y = margin

        for i, line in enumerate(self._lines):
            if i < self._scroll_y:
                continue
            if y > h:
                break

            if line and not line.startswith(' ') and ':' in line:
                dc.SetTextForeground(wx.Colour(*T.TEXT_SECONDARY))
                dc.SetFont(T.get_font_accent(9))
            else:
                dc.SetTextForeground(wx.Colour(*T.TEXT_PRIMARY))
                dc.SetFont(T.get_font_primary(9))

            dc.DrawText(line, margin, y)
            y += self._line_height

        total_lines = len(self._lines)
        visible_lines = h // self._line_height
        if total_lines > visible_lines:
            scrollbar_height = max(20, int(h * visible_lines / total_lines))
            scrollbar_y = int((h - scrollbar_height) * self._scroll_y / max(1, total_lines - visible_lines))
            dc.SetBrush(wx.Brush(wx.Colour(*T.BG_HOVER)))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(w - 6, scrollbar_y, 4, scrollbar_height)


class PreviewPanel(wx.Panel if wx else object):

    def __init__(self, parent):
        if wx is None:
            raise ImportError("wxPython is not available")

        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(*Theme.BG_ELEVATED))

        self.component: Optional[ComponentInfo] = None
        self.symbol_converter = SymbolConverter()
        self.footprint_converter = FootprintConverter()

        self._init_ui()

    def _init_ui(self):
        T = Theme
        sizer = wx.BoxSizer(wx.VERTICAL)

        tab_bar = wx.Panel(self)
        tab_bar.SetBackgroundColour(wx.Colour(*T.BG_ELEVATED))
        tab_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.tab_symbol = TabButton(tab_bar, "Symbol")
        self.tab_symbol.SetCallback(lambda: self._select_tab(0))
        tab_sizer.Add(self.tab_symbol, 0, wx.RIGHT, 1)

        self.tab_footprint = TabButton(tab_bar, "Footprint")
        self.tab_footprint.SetCallback(lambda: self._select_tab(1))
        tab_sizer.Add(self.tab_footprint, 0, wx.RIGHT, 1)

        self.tab_3dmodel = TabButton(tab_bar, "3D Model")
        self.tab_3dmodel.SetCallback(lambda: self._select_tab(2))
        tab_sizer.Add(self.tab_3dmodel, 0, wx.RIGHT, 1)

        self.tab_data = TabButton(tab_bar, "Data")
        self.tab_data.SetCallback(lambda: self._select_tab(3))
        tab_sizer.Add(self.tab_data, 0, wx.RIGHT, 1)

        self.tab_buttons = [self.tab_symbol, self.tab_footprint, self.tab_3dmodel, self.tab_data]

        tab_sizer.AddStretchSpacer()
        tab_bar.SetSizer(tab_sizer)
        sizer.Add(tab_bar, 0, wx.EXPAND | wx.BOTTOM, 1)

        self.content_panel = wx.Panel(self)
        self.content_panel.SetBackgroundColour(wx.Colour(*T.BG_DARKEST))
        self.content_sizer = wx.BoxSizer(wx.VERTICAL)

        self.symbol_panel = SymbolPreviewPanel(self.content_panel)
        self.content_sizer.Add(self.symbol_panel, 1, wx.EXPAND)

        self.footprint_panel = FootprintPreviewPanel(self.content_panel)
        self.content_sizer.Add(self.footprint_panel, 1, wx.EXPAND)

        self.model3d_panel = Model3DPreviewPanel(self.content_panel)
        self.content_sizer.Add(self.model3d_panel, 1, wx.EXPAND)

        self.info_panel = DataInfoPanel(self.content_panel)
        self.content_sizer.Add(self.info_panel, 1, wx.EXPAND)

        self.content_panel.SetSizer(self.content_sizer)
        sizer.Add(self.content_panel, 1, wx.EXPAND)

        self.SetSizer(sizer)

        self._panels = [self.symbol_panel, self.footprint_panel, self.model3d_panel, self.info_panel]
        self._select_tab(0)

    def _select_tab(self, idx):
        for i, btn in enumerate(self.tab_buttons):
            btn.SetSelected(i == idx)

        for i, panel in enumerate(self._panels):
            panel.Show(i == idx)

        self.content_panel.Layout()

    def set_component(self, component: ComponentInfo):
        self.component = component

        if component.has_symbol():
            try:
                symbol = self.symbol_converter.convert(
                    component.symbol_data,
                    component_name=component.mpn or component.lcsc_id
                )
                if symbol:
                    self.symbol_panel.set_symbol(symbol)
                else:
                    self.symbol_panel.clear()
            except Exception as e:
                logger.error(f"Error parsing symbol: {e}")
                self.symbol_panel.clear()
        else:
            self.symbol_panel.clear()

        if component.has_footprint():
            try:
                footprint = self.footprint_converter.convert(
                    component.footprint_data,
                    component_name=component.mpn or component.lcsc_id
                )
                if footprint:
                    self.footprint_panel.set_footprint(footprint)
                else:
                    self.footprint_panel.clear()
            except Exception as e:
                logger.error(f"Error parsing footprint: {e}")
                self.footprint_panel.clear()
        else:
            self.footprint_panel.clear()

        if component.has_3d_model():
            from ..converters.model3d_handler import Model3DHandler
            handler = Model3DHandler()
            model_path = handler.get_model_path(component.lcsc_id)
            self.model3d_panel.set_model(
                component.model_3d_uuid,
                component.lcsc_id,
                model_path
            )
        else:
            self.model3d_panel.clear()

        self._update_info_text(component)

    def _update_info_text(self, component: ComponentInfo):
        info = []
        info.append(f"LCSC Part Number: {component.lcsc_id}")
        info.append(f"MPN: {component.mpn or 'N/A'}")
        info.append(f"Manufacturer: {component.manufacturer or 'N/A'}")
        info.append(f"")
        info.append(f"Description:")
        info.append(f"  {component.description or 'N/A'}")
        info.append(f"")
        info.append(f"Package: {component.package or 'N/A'}")
        info.append(f"Category: {component.category or 'N/A'}")
        info.append(f"")
        info.append(f"Available Assets:")
        info.append(f"  Symbol:    {'Yes' if component.has_symbol() else 'No'}")
        info.append(f"  Footprint: {'Yes' if component.has_footprint() else 'No'}")
        info.append(f"  3D Model:  {'Yes' if component.has_3d_model() else 'No'}")

        if component.datasheet_url:
            info.append(f"")
            info.append(f"Datasheet: {component.datasheet_url}")

        self.info_panel.set_info("\n".join(info))

    def clear(self):
        self.component = None
        self.symbol_panel.clear()
        self.footprint_panel.clear()
        self.model3d_panel.clear()
        self.info_panel.clear()
