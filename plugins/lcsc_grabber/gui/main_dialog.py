import logging
import threading
from typing import Optional, List

try:
    import wx
    import wx.adv
except ImportError:
    wx = None

from ..api.easyeda_client import EasyEdaClient, EasyEdaApiError
from ..api.cache import CacheManager, get_cache
from ..api.models import ComponentInfo
from ..kicad.library_manager import LibraryManager, get_library_manager
from .preview_panel import PreviewPanel, Model3DPreviewPanel
from .library_manager_dialog import show_library_manager_dialog


logger = logging.getLogger(__name__)


class Theme:

    BG_DARKEST = wx.Colour(22, 22, 26) if wx else None
    BG_BASE = wx.Colour(28, 28, 32) if wx else None
    BG_ELEVATED = wx.Colour(38, 38, 44) if wx else None
    BG_HOVER = wx.Colour(50, 50, 58) if wx else None

    TEXT_PRIMARY = wx.Colour(210, 210, 215) if wx else None
    TEXT_SECONDARY = wx.Colour(130, 130, 145) if wx else None
    TEXT_DISABLED = wx.Colour(80, 80, 92) if wx else None

    ACCENT = wx.Colour(100, 140, 180) if wx else None
    ACCENT_HOVER = wx.Colour(120, 160, 200) if wx else None
    ACCENT_DIM = wx.Colour(80, 110, 140) if wx else None
    ACCENT_GLOW = wx.Colour(100, 140, 180, 40) if wx else None

    BORDER_SUBTLE = wx.Colour(50, 50, 58) if wx else None
    BORDER_ACCENT = wx.Colour(80, 110, 140) if wx else None

    SUCCESS = wx.Colour(90, 160, 90) if wx else None
    ERROR = wx.Colour(180, 80, 80) if wx else None
    WARNING = wx.Colour(200, 160, 60) if wx else None

    PADDING = 10
    BORDER_WIDTH = 1

    @staticmethod
    def get_font_primary(size=9, bold=False):
        weight = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
        return wx.Font(size, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, weight)

    @staticmethod
    def get_font_accent(size=9, bold=False):
        weight = wx.FONTWEIGHT_BOLD if bold else wx.FONTWEIGHT_NORMAL
        return wx.Font(size, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, weight)


def draw_subtle_border(dc, rect):
    dc.SetPen(wx.Pen(Theme.BORDER_SUBTLE, 1))
    dc.SetBrush(wx.TRANSPARENT_BRUSH)
    dc.DrawRectangle(rect.x, rect.y, rect.width, rect.height)


class WindowControlButton(wx.Panel):

    def __init__(self, parent, symbol="×", action=None, is_close=False):
        super().__init__(parent, style=wx.NO_BORDER)
        self.symbol = symbol
        self.action = action
        self.is_close = is_close
        self._hover = False

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((32, 28))

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_click)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        if self._hover:
            if self.is_close:
                dc.SetBrush(wx.Brush(T.ERROR))
            else:
                dc.SetBrush(wx.Brush(T.BG_HOVER))
        else:
            dc.SetBrush(wx.Brush(T.BG_ELEVATED))

        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, w, h)

        dc.SetFont(T.get_font_accent(12))
        if self._hover and self.is_close:
            dc.SetTextForeground(T.TEXT_PRIMARY)
        elif self._hover:
            dc.SetTextForeground(T.TEXT_PRIMARY)
        else:
            dc.SetTextForeground(T.TEXT_SECONDARY)

        tw, th = dc.GetTextExtent(self.symbol)
        dc.DrawText(self.symbol, (w - tw) // 2, (h - th) // 2)

    def _on_click(self, event):
        if self.action:
            self.action()

    def _on_enter(self, event):
        self._hover = True
        self.Refresh()

    def _on_leave(self, event):
        self._hover = False
        self.Refresh()


class DraggableHeader(wx.Panel):

    def __init__(self, parent, title="", version="", on_close=None, on_minimize=None):
        super().__init__(parent, style=wx.NO_BORDER)
        self.title = title
        self.version = version
        self._dragging = False
        self._drag_start = None

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((-1, 36))

        sizer = wx.BoxSizer(wx.HORIZONTAL)

        sizer.AddStretchSpacer()

        if on_minimize:
            self.minimize_btn = WindowControlButton(self, "─", on_minimize)
            sizer.Add(self.minimize_btn, 0)

        if on_close:
            self.close_btn = WindowControlButton(self, "×", on_close, is_close=True)
            sizer.Add(self.close_btn, 0)

        self.SetSizer(sizer)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_mouse_up)
        self.Bind(wx.EVT_MOTION, self._on_mouse_motion)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_double_click)

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.Brush(T.BG_ELEVATED))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, w, h)

        dc.SetPen(wx.Pen(T.BORDER_SUBTLE, 1))
        dc.DrawLine(0, h - 1, w, h - 1)

        dc.SetFont(T.get_font_accent(11, bold=True))
        dc.SetTextForeground(T.TEXT_PRIMARY)
        tw, th = dc.GetTextExtent(self.title)
        dc.DrawText(self.title, 12, (h - th) // 2 - 1)

        if self.version:
            dc.SetFont(T.get_font_accent(9))
            dc.SetTextForeground(T.TEXT_DISABLED)
            vw, vh = dc.GetTextExtent(self.version)
            dc.DrawText(self.version, 12 + tw + 12, (h - vh) // 2 - 1)

    def _on_mouse_down(self, event):
        pos = event.GetPosition()
        w, h = self.GetSize()
        if pos.x < w - 70:
            self._dragging = True
            self._drag_start = event.GetPosition()
            self.CaptureMouse()

    def _on_mouse_up(self, event):
        if self._dragging:
            self._dragging = False
            if self.HasCapture():
                self.ReleaseMouse()

    def _on_mouse_motion(self, event):
        if self._dragging and self._drag_start:
            pos = event.GetPosition()
            delta = pos - self._drag_start
            window = self.GetTopLevelParent()
            window_pos = window.GetPosition()
            window.SetPosition(window_pos + delta)

    def _on_double_click(self, event):
        pass


class SectionHeader(wx.Panel):

    def __init__(self, parent, label=""):
        super().__init__(parent, style=wx.NO_BORDER)
        self.label = label
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((-1, 22))
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.Brush(T.BG_ELEVATED))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, w, h)

        square_size = 6
        dc.SetBrush(wx.Brush(T.ACCENT))
        dc.DrawRectangle(0, (h - square_size) // 2, square_size, square_size)

        dc.SetFont(T.get_font_accent(9))
        dc.SetTextForeground(T.TEXT_SECONDARY)
        label_text = self.label.upper()
        tw, th = dc.GetTextExtent(label_text)
        dc.DrawText(label_text, 12, (h - th) // 2)


class PrimaryButton(wx.Panel):

    def __init__(self, parent, label="", id=wx.ID_ANY):
        super().__init__(parent, id, style=wx.NO_BORDER)
        self.label = label
        self._pressed = False
        self._hover = False
        self._enabled = True

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((90, 28))

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_mouse_up)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        if not self._enabled:
            dc.SetBrush(wx.Brush(T.BG_HOVER))
            dc.SetPen(wx.Pen(T.BORDER_SUBTLE, 1))
            dc.SetTextForeground(T.TEXT_DISABLED)
        elif self._pressed:
            dc.SetBrush(wx.Brush(T.ACCENT_DIM))
            dc.SetPen(wx.Pen(T.ACCENT_DIM, 1))
            dc.SetTextForeground(T.TEXT_PRIMARY)
        elif self._hover:
            dc.SetBrush(wx.Brush(T.ACCENT_HOVER))
            dc.SetPen(wx.Pen(T.ACCENT_HOVER, 1))
            dc.SetTextForeground(T.BG_DARKEST)
        else:
            dc.SetBrush(wx.Brush(T.ACCENT))
            dc.SetPen(wx.Pen(T.ACCENT, 1))
            dc.SetTextForeground(T.BG_DARKEST)

        dc.DrawRectangle(0, 0, w, h)

        dc.SetFont(T.get_font_accent(9, bold=True))
        tw, th = dc.GetTextExtent(self.label)
        dc.DrawText(self.label, (w - tw) // 2, (h - th) // 2)

    def _on_mouse_down(self, event):
        if self._enabled:
            self._pressed = True
            self.CaptureMouse()
            self.Refresh()

    def _on_mouse_up(self, event):
        was_pressed = self._pressed
        self._pressed = False
        if self.HasCapture():
            self.ReleaseMouse()
        self.Refresh()
        if was_pressed and self._enabled:
            evt = wx.CommandEvent(wx.wxEVT_BUTTON, self.GetId())
            evt.SetEventObject(self)
            wx.PostEvent(self, evt)

    def _on_enter(self, event):
        self._hover = True
        self.Refresh()

    def _on_leave(self, event):
        self._hover = False
        self._pressed = False
        self.Refresh()

    def Enable(self, enable=True):
        self._enabled = enable
        self.Refresh()

    def Disable(self):
        self.Enable(False)

    def SetLabel(self, label):
        self.label = label
        self.Refresh()


class SecondaryButton(wx.Panel):

    def __init__(self, parent, label="", id=wx.ID_ANY):
        super().__init__(parent, id, style=wx.NO_BORDER)
        self.label = label
        self._pressed = False
        self._hover = False
        self._enabled = True

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((80, 28))

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_mouse_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_mouse_up)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        if not self._enabled:
            dc.SetBrush(wx.Brush(T.BG_ELEVATED))
            dc.SetPen(wx.Pen(T.BORDER_SUBTLE, 1))
            dc.SetTextForeground(T.TEXT_DISABLED)
        elif self._pressed:
            dc.SetBrush(wx.Brush(T.BG_HOVER))
            dc.SetPen(wx.Pen(T.ACCENT_DIM, 1))
            dc.SetTextForeground(T.ACCENT)
        elif self._hover:
            dc.SetBrush(wx.Brush(T.BG_HOVER))
            dc.SetPen(wx.Pen(T.ACCENT, 1))
            dc.SetTextForeground(T.ACCENT)
        else:
            dc.SetBrush(wx.Brush(T.BG_ELEVATED))
            dc.SetPen(wx.Pen(T.BORDER_SUBTLE, 1))
            dc.SetTextForeground(T.TEXT_SECONDARY)

        dc.DrawRectangle(0, 0, w, h)

        dc.SetFont(T.get_font_accent(9))
        tw, th = dc.GetTextExtent(self.label)
        dc.DrawText(self.label, (w - tw) // 2, (h - th) // 2)

    def _on_mouse_down(self, event):
        if self._enabled:
            self._pressed = True
            self.CaptureMouse()
            self.Refresh()

    def _on_mouse_up(self, event):
        was_pressed = self._pressed
        self._pressed = False
        if self.HasCapture():
            self.ReleaseMouse()
        self.Refresh()
        if was_pressed and self._enabled:
            evt = wx.CommandEvent(wx.wxEVT_BUTTON, self.GetId())
            evt.SetEventObject(self)
            wx.PostEvent(self, evt)

    def _on_enter(self, event):
        self._hover = True
        self.Refresh()

    def _on_leave(self, event):
        self._hover = False
        self._pressed = False
        self.Refresh()

    def Enable(self, enable=True):
        self._enabled = enable
        self.Refresh()

    def Disable(self):
        self.Enable(False)

    def SetLabel(self, label):
        self.label = label
        self.Refresh()


class RetroStatusBar(wx.Panel):

    def __init__(self, parent):
        super().__init__(parent, style=wx.NO_BORDER)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((-1, 26))

        self._message = "Ready"
        self._status_type = "info"
        self._cache_count = 0

        self.Bind(wx.EVT_PAINT, self._on_paint)

    def set_status(self, message: str, status_type: str = "info"):
        self._message = message
        self._status_type = status_type
        self.Refresh()

    def set_cache_count(self, count: int):
        self._cache_count = count
        self.Refresh()

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.Brush(T.BG_DARKEST))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, w, h)

        dc.SetFont(T.get_font_accent(9))
        y_center = (h - dc.GetTextExtent("X")[1]) // 2

        if self._status_type == "error":
            indicator_color = T.ERROR
        elif self._status_type == "success":
            indicator_color = T.SUCCESS
        else:
            indicator_color = T.ACCENT

        dc.SetBrush(wx.Brush(indicator_color))
        dc.SetPen(wx.TRANSPARENT_PEN)
        square_size = 6
        dc.DrawRectangle(10, (h - square_size) // 2, square_size, square_size)

        if self._status_type == "error":
            dc.SetTextForeground(T.ERROR)
        elif self._status_type == "success":
            dc.SetTextForeground(T.SUCCESS)
        else:
            dc.SetTextForeground(T.TEXT_SECONDARY)

        x = 22
        dc.DrawText(self._message[:80], x, y_center)

        right_text = f"│ Cache: {self._cache_count}"
        dc.SetTextForeground(T.TEXT_DISABLED)
        rw, rh = dc.GetTextExtent(right_text)
        dc.DrawText(right_text, w - rw - 10, y_center)


class ElevatedPanel(wx.Panel):

    def __init__(self, parent, style=wx.NO_BORDER):
        super().__init__(parent, style=style)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.Brush(T.BG_ELEVATED))
        dc.SetPen(wx.Pen(T.BORDER_SUBTLE, 1))
        dc.DrawRectangle(0, 0, w, h)


class DataListPanel(wx.ScrolledWindow):

    def __init__(self, parent):
        super().__init__(parent, style=wx.VSCROLL | wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(wx.Colour(*Theme.BG_DARKEST) if isinstance(Theme.BG_DARKEST, tuple) else Theme.BG_DARKEST)

        self._items = []
        self._row_height = 24
        self._selected = -1

        self.SetScrollRate(0, self._row_height)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_click)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _on_size(self, event):
        self._update_scroll()
        self.Refresh()
        event.Skip()

    def _update_scroll(self):
        h = len(self._items) * self._row_height
        self.SetVirtualSize((self.GetClientSize().width, max(h, 1)))

    def set_items(self, items):
        self._items = items
        self._selected = -1
        self._update_scroll()
        self.Scroll(0, 0)
        self.Refresh()

    def clear(self):
        self._items = []
        self._selected = -1
        self._update_scroll()
        self.Refresh()

    def _on_click(self, event):
        pos = self.CalcUnscrolledPosition(event.GetPosition())
        row = pos.y // self._row_height
        if 0 <= row < len(self._items):
            self._selected = row
            self.Refresh()

    def _on_paint(self, event):
        dc = wx.AutoBufferedPaintDC(self)
        self.DoPrepareDC(dc)
        T = Theme

        w, h = self.GetVirtualSize()
        client_w = self.GetClientSize().width

        dc.SetBrush(wx.Brush(T.BG_DARKEST))
        dc.SetPen(wx.TRANSPARENT_PEN)
        dc.DrawRectangle(0, 0, client_w, max(h, self.GetClientSize().height))

        if not self._items:
            dc.SetFont(T.get_font_accent(10))
            dc.SetTextForeground(T.ACCENT_DIM)
            text = "No component selected"
            tw, th = dc.GetTextExtent(text)
            ch = self.GetClientSize().height
            dc.DrawText(text, (client_w - tw) // 2, (ch - th) // 2 - 10)

            dc.SetFont(T.get_font_primary(9))
            dc.SetTextForeground(T.TEXT_DISABLED)
            hint = "Search for a part number"
            tw2, th2 = dc.GetTextExtent(hint)
            dc.DrawText(hint, (client_w - tw2) // 2, (ch - th) // 2 + 12)
            return

        field_width = 110
        for i, (field, value) in enumerate(self._items):
            y = i * self._row_height

            if i == self._selected:
                dc.SetBrush(wx.Brush(T.BG_HOVER))
                dc.SetPen(wx.TRANSPARENT_PEN)
                dc.DrawRectangle(0, y, client_w, self._row_height)

            elif i % 2 == 1:
                dc.SetBrush(wx.Brush(T.BG_ELEVATED))
                dc.SetPen(wx.TRANSPARENT_PEN)
                dc.DrawRectangle(0, y, client_w, self._row_height)

            dc.SetFont(T.get_font_accent(9))
            dc.SetTextForeground(T.TEXT_SECONDARY)
            dc.DrawText(field, 8, y + (self._row_height - 14) // 2)

            dc.SetFont(T.get_font_primary(9))
            dc.SetTextForeground(T.TEXT_PRIMARY)
            val_str = str(value) if value else "N/A"
            max_val_width = client_w - field_width - 16
            tw, th = dc.GetTextExtent(val_str)
            if tw > max_val_width and len(val_str) > 3:
                while tw > max_val_width and len(val_str) > 3:
                    val_str = val_str[:-4] + "..."
                    tw, th = dc.GetTextExtent(val_str)
            dc.DrawText(val_str, field_width, y + (self._row_height - 14) // 2)


class LCSCGrabberDialog(wx.Dialog if wx else object):

    def __init__(self, parent):
        if wx is None:
            raise ImportError("wxPython is not available")

        super().__init__(
            parent,
            title="LCSC Grabber",
            size=(1000, 700),
            style=wx.NO_BORDER | wx.FRAME_SHAPED
        )

        self._resizing = False
        self._resize_start = None
        self._resize_start_size = None

        self.client = EasyEdaClient()
        self.cache = get_cache()
        self.library_manager = get_library_manager()

        self.current_component: Optional[ComponentInfo] = None
        self.search_history: List[str] = self.cache.get_search_history()

        self._init_ui()
        self._bind_events()
        self._update_status("Ready. Enter an LCSC part number to search.")

    def _init_ui(self):
        T = Theme
        PAD = T.PADDING

        self.SetBackgroundColour(T.BG_BASE)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        self._draw_border = True

        header_panel = DraggableHeader(
            self,
            title="LCSC GRABBER",
            version="v1.0",
            on_close=self._on_close,
            on_minimize=self._on_minimize
        )
        main_sizer.Add(header_panel, 0, wx.EXPAND)

        search_panel = wx.Panel(self)
        search_panel.SetBackgroundColour(T.BG_ELEVATED)
        search_sizer = wx.BoxSizer(wx.HORIZONTAL)

        search_label = wx.StaticText(search_panel, label="Part Number:")
        search_label.SetForegroundColour(T.TEXT_SECONDARY)
        search_label.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        search_sizer.Add(search_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, PAD)

        self.search_ctrl = wx.TextCtrl(search_panel, style=wx.TE_PROCESS_ENTER | wx.BORDER_SIMPLE)
        self.search_ctrl.SetBackgroundColour(T.BG_DARKEST)
        self.search_ctrl.SetForegroundColour(T.TEXT_PRIMARY)
        self.search_ctrl.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        self.search_ctrl.SetHint("C123456 or MPN")
        self.search_ctrl.SetMinSize((250, 28))
        search_sizer.Add(self.search_ctrl, 1, wx.ALL | wx.EXPAND, 6)

        self.search_btn = PrimaryButton(search_panel, label="Search")
        self.search_btn.SetMinSize((90, 30))
        search_sizer.Add(self.search_btn, 0, wx.ALL, 6)

        self.clear_btn = SecondaryButton(search_panel, label="Clear")
        self.clear_btn.SetMinSize((70, 30))
        search_sizer.Add(self.clear_btn, 0, wx.ALL, 6)

        search_panel.SetSizer(search_sizer)
        main_sizer.Add(search_panel, 0, wx.EXPAND | wx.TOP, 1)

        content_sizer = wx.BoxSizer(wx.HORIZONTAL)

        left_panel = ElevatedPanel(self)
        left_sizer = wx.BoxSizer(wx.VERTICAL)

        info_header = SectionHeader(left_panel, label="Component Data")
        left_sizer.Add(info_header, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, PAD)

        self.info_list = DataListPanel(left_panel)
        left_sizer.Add(self.info_list, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PAD)

        self.datasheet_link = wx.adv.HyperlinkCtrl(left_panel, label="Open Datasheet", url="")
        self.datasheet_link.SetNormalColour(T.ACCENT)
        self.datasheet_link.SetHoverColour(T.ACCENT_HOVER)
        self.datasheet_link.SetVisitedColour(T.ACCENT_DIM)
        self.datasheet_link.Hide()
        left_sizer.Add(self.datasheet_link, 0, wx.LEFT | wx.BOTTOM, PAD)

        left_panel.SetSizer(left_sizer)

        right_panel = ElevatedPanel(self)
        right_sizer = wx.BoxSizer(wx.VERTICAL)

        preview_header = SectionHeader(right_panel, label="Preview")
        right_sizer.Add(preview_header, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, PAD)

        self.preview_panel = PreviewPanel(right_panel)
        right_sizer.Add(self.preview_panel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PAD)

        right_panel.SetSizer(right_sizer)

        content_sizer.Add(left_panel, 38, wx.EXPAND | wx.ALL, 4)
        content_sizer.Add(right_panel, 62, wx.EXPAND | wx.ALL, 4)

        main_sizer.Add(content_sizer, 1, wx.EXPAND)

        # Category selection panel
        cat_panel = wx.Panel(self)
        cat_panel.SetBackgroundColour(T.BG_ELEVATED)
        cat_sizer = wx.BoxSizer(wx.HORIZONTAL)

        cat_lbl = wx.StaticText(cat_panel, label="Category:")
        cat_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        cat_lbl.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        cat_sizer.Add(cat_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, PAD)

        self.category_combo = wx.ComboBox(cat_panel, style=wx.CB_READONLY)
        self.category_combo.SetBackgroundColour(T.BG_DARKEST)
        self.category_combo.SetForegroundColour(T.TEXT_PRIMARY)
        self.category_combo.SetMinSize((200, 28))
        self._populate_categories()
        cat_sizer.Add(self.category_combo, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)

        self.add_category_btn = SecondaryButton(cat_panel, label="+")
        self.add_category_btn.SetMinSize((32, 28))
        cat_sizer.Add(self.add_category_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 2)

        cat_sizer.AddStretchSpacer()

        cat_panel.SetSizer(cat_sizer)
        main_sizer.Add(cat_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)

        # Import options panel
        opt_panel = wx.Panel(self)
        opt_panel.SetBackgroundColour(T.BG_ELEVATED)
        opt_sizer = wx.BoxSizer(wx.HORIZONTAL)

        opt_lbl = wx.StaticText(opt_panel, label="Import:")
        opt_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        opt_lbl.SetFont(wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        opt_sizer.Add(opt_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, PAD)

        self.chk_symbol = wx.CheckBox(opt_panel, label="Symbol")
        self.chk_symbol.SetForegroundColour(T.TEXT_PRIMARY)
        self.chk_symbol.SetValue(True)
        opt_sizer.Add(self.chk_symbol, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)

        self.chk_footprint = wx.CheckBox(opt_panel, label="Footprint")
        self.chk_footprint.SetForegroundColour(T.TEXT_PRIMARY)
        self.chk_footprint.SetValue(True)
        opt_sizer.Add(self.chk_footprint, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)

        self.chk_3d_model = wx.CheckBox(opt_panel, label="3D Model")
        self.chk_3d_model.SetForegroundColour(T.TEXT_PRIMARY)
        self.chk_3d_model.SetValue(True)
        opt_sizer.Add(self.chk_3d_model, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 6)

        opt_sizer.AddStretchSpacer()

        self.chk_overwrite = wx.CheckBox(opt_panel, label="Overwrite existing")
        self.chk_overwrite.SetForegroundColour(T.TEXT_SECONDARY)
        opt_sizer.Add(self.chk_overwrite, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, PAD)

        opt_panel.SetSizer(opt_sizer)
        main_sizer.Add(opt_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        # 3D Model Configuration Panel
        self.model3d_panel = wx.Panel(self)
        self.model3d_panel.SetBackgroundColour(T.BG_ELEVATED)
        model3d_sizer = wx.BoxSizer(wx.VERTICAL)

        # Header row with expand/collapse toggle
        model3d_header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.model3d_toggle_btn = SecondaryButton(self.model3d_panel, label="▼ 3D Model Config")
        self.model3d_toggle_btn.SetMinSize((140, 24))
        model3d_header_sizer.Add(self.model3d_toggle_btn, 0, wx.ALL, 4)
        model3d_header_sizer.AddStretchSpacer()

        self.model3d_reset_btn = SecondaryButton(self.model3d_panel, label="Reset Auto")
        self.model3d_reset_btn.SetMinSize((80, 24))
        model3d_header_sizer.Add(self.model3d_reset_btn, 0, wx.ALL, 4)

        model3d_sizer.Add(model3d_header_sizer, 0, wx.EXPAND)

        # Collapsible content panel
        self.model3d_content = wx.Panel(self.model3d_panel)
        self.model3d_content.SetBackgroundColour(T.BG_ELEVATED)
        content_sizer = wx.BoxSizer(wx.VERTICAL)

        # Controls row
        controls_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Rotation controls
        rot_box = wx.StaticBox(self.model3d_content, label="Rotation (degrees)")
        rot_box.SetForegroundColour(T.TEXT_SECONDARY)
        rot_sizer = wx.StaticBoxSizer(rot_box, wx.HORIZONTAL)

        rot_x_lbl = wx.StaticText(self.model3d_content, label="X:")
        rot_x_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        rot_sizer.Add(rot_x_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.rot_x_ctrl = wx.SpinCtrlDouble(self.model3d_content, min=-360, max=360, initial=0, inc=1)
        self.rot_x_ctrl.SetDigits(1)
        self.rot_x_ctrl.SetMinSize((70, -1))
        rot_sizer.Add(self.rot_x_ctrl, 0, wx.ALL, 2)

        rot_y_lbl = wx.StaticText(self.model3d_content, label="Y:")
        rot_y_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        rot_sizer.Add(rot_y_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.rot_y_ctrl = wx.SpinCtrlDouble(self.model3d_content, min=-360, max=360, initial=0, inc=1)
        self.rot_y_ctrl.SetDigits(1)
        self.rot_y_ctrl.SetMinSize((70, -1))
        rot_sizer.Add(self.rot_y_ctrl, 0, wx.ALL, 2)

        rot_z_lbl = wx.StaticText(self.model3d_content, label="Z:")
        rot_z_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        rot_sizer.Add(rot_z_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.rot_z_ctrl = wx.SpinCtrlDouble(self.model3d_content, min=-360, max=360, initial=0, inc=1)
        self.rot_z_ctrl.SetDigits(1)
        self.rot_z_ctrl.SetMinSize((70, -1))
        rot_sizer.Add(self.rot_z_ctrl, 0, wx.ALL, 2)

        controls_sizer.Add(rot_sizer, 0, wx.ALL, 4)

        # Offset controls
        off_box = wx.StaticBox(self.model3d_content, label="Offset (mm)")
        off_box.SetForegroundColour(T.TEXT_SECONDARY)
        off_sizer = wx.StaticBoxSizer(off_box, wx.HORIZONTAL)

        off_x_lbl = wx.StaticText(self.model3d_content, label="X:")
        off_x_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        off_sizer.Add(off_x_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.off_x_ctrl = wx.SpinCtrlDouble(self.model3d_content, min=-100, max=100, initial=0, inc=0.1)
        self.off_x_ctrl.SetDigits(2)
        self.off_x_ctrl.SetMinSize((70, -1))
        off_sizer.Add(self.off_x_ctrl, 0, wx.ALL, 2)

        off_y_lbl = wx.StaticText(self.model3d_content, label="Y:")
        off_y_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        off_sizer.Add(off_y_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.off_y_ctrl = wx.SpinCtrlDouble(self.model3d_content, min=-100, max=100, initial=0, inc=0.1)
        self.off_y_ctrl.SetDigits(2)
        self.off_y_ctrl.SetMinSize((70, -1))
        off_sizer.Add(self.off_y_ctrl, 0, wx.ALL, 2)

        off_z_lbl = wx.StaticText(self.model3d_content, label="Z:")
        off_z_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        off_sizer.Add(off_z_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.off_z_ctrl = wx.SpinCtrlDouble(self.model3d_content, min=-100, max=100, initial=0, inc=0.1)
        self.off_z_ctrl.SetDigits(2)
        self.off_z_ctrl.SetMinSize((70, -1))
        off_sizer.Add(self.off_z_ctrl, 0, wx.ALL, 2)

        controls_sizer.Add(off_sizer, 0, wx.ALL, 4)
        content_sizer.Add(controls_sizer, 0, wx.EXPAND)

        # Mini 3D preview panel
        self.config_3d_preview = Model3DPreviewPanel(self.model3d_content)
        self.config_3d_preview.SetMinSize((-1, 150))
        content_sizer.Add(self.config_3d_preview, 1, wx.EXPAND | wx.ALL, 4)

        # Bind spin controls to update preview
        self.rot_x_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_model3d_config_changed)
        self.rot_y_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_model3d_config_changed)
        self.rot_z_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_model3d_config_changed)
        self.off_x_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_model3d_config_changed)
        self.off_y_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_model3d_config_changed)
        self.off_z_ctrl.Bind(wx.EVT_SPINCTRLDOUBLE, self._on_model3d_config_changed)

        self.model3d_content.SetSizer(content_sizer)
        model3d_sizer.Add(self.model3d_content, 0, wx.EXPAND)

        self.model3d_panel.SetSizer(model3d_sizer)
        self.model3d_content.Hide()  # Start collapsed
        self._model3d_expanded = False
        main_sizer.Add(self.model3d_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)

        btn_panel = wx.Panel(self)
        btn_panel.SetBackgroundColour(T.BG_ELEVATED)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)

        lib_path = self.library_manager.get_library_path()
        self.lib_path_label = wx.StaticText(btn_panel, label=f"Library: {lib_path}")
        self.lib_path_label.SetForegroundColour(T.TEXT_DISABLED)
        self.lib_path_label.SetFont(wx.Font(8, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL))
        btn_sizer.Add(self.lib_path_label, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, PAD)

        self.manage_lib_btn = SecondaryButton(btn_panel, label="Manage Library")
        self.manage_lib_btn.SetMinSize((110, 30))
        btn_sizer.Add(self.manage_lib_btn, 0, wx.ALL, 6)

        self.import_btn = PrimaryButton(btn_panel, label="Import")
        self.import_btn.SetMinSize((90, 30))
        self.import_btn.Enable(False)
        btn_sizer.Add(self.import_btn, 0, wx.ALL, 6)

        self.close_btn = SecondaryButton(btn_panel, label="Close")
        self.close_btn.SetMinSize((70, 30))
        btn_sizer.Add(self.close_btn, 0, wx.ALL, 6)

        btn_panel.SetSizer(btn_sizer)
        main_sizer.Add(btn_panel, 0, wx.EXPAND | wx.ALL, 4)

        self.status_bar = RetroStatusBar(self)
        self.status_bar.set_cache_count(len(self.cache.get_search_history()))
        main_sizer.Add(self.status_bar, 0, wx.EXPAND)

        self.SetSizer(main_sizer)
        self.Centre()

    def _bind_events(self):
        self.search_btn.Bind(wx.EVT_BUTTON, self._on_search)
        self.search_ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_search)
        self.clear_btn.Bind(wx.EVT_BUTTON, self._on_clear)
        self.import_btn.Bind(wx.EVT_BUTTON, self._on_import)
        self.close_btn.Bind(wx.EVT_BUTTON, self._on_close_btn)
        self.add_category_btn.Bind(wx.EVT_BUTTON, self._on_add_category)
        self.model3d_toggle_btn.Bind(wx.EVT_BUTTON, self._on_toggle_model3d)
        self.model3d_reset_btn.Bind(wx.EVT_BUTTON, self._on_reset_model3d)
        self.manage_lib_btn.Bind(wx.EVT_BUTTON, self._on_manage_library)
        self.Bind(wx.EVT_CLOSE, self._on_close_evt)
        self.Bind(wx.EVT_PAINT, self._on_paint_border)

    def _on_manage_library(self, event):
        show_library_manager_dialog(self, self.library_manager)
        # Refresh categories in case they were modified
        self._populate_categories()

    def _on_toggle_model3d(self, event):
        self._model3d_expanded = not self._model3d_expanded
        if self._model3d_expanded:
            self.model3d_content.Show()
            self.model3d_toggle_btn.SetLabel("▲ 3D Model Config")
        else:
            self.model3d_content.Hide()
            self.model3d_toggle_btn.SetLabel("▼ 3D Model Config")
        self.model3d_toggle_btn.Refresh()
        self.Layout()
        self.Refresh()

    def _on_reset_model3d(self, event):
        if self.current_component and self.current_component.has_3d_model():
            self._calculate_and_set_model3d_values(self.current_component)

    def _calculate_and_set_model3d_values(self, component: ComponentInfo):
        if not component.has_footprint():
            return

        try:
            footprint = self.library_manager.footprint_converter.convert(
                component.footprint_data,
                component_name=component.mpn or component.lcsc_id
            )
            if footprint:
                offset, rotation, scale = self.library_manager.model3d_config.calculate_transform(
                    component.lcsc_id, footprint
                )
                self.off_x_ctrl.SetValue(offset[0])
                self.off_y_ctrl.SetValue(offset[1])
                self.off_z_ctrl.SetValue(offset[2])
                self.rot_x_ctrl.SetValue(rotation[0])
                self.rot_y_ctrl.SetValue(rotation[1])
                self.rot_z_ctrl.SetValue(rotation[2])
        except Exception as e:
            logger.warning(f"Could not calculate 3D transform: {e}")

    def _get_model3d_values(self):
        offset = (
            self.off_x_ctrl.GetValue(),
            self.off_y_ctrl.GetValue(),
            self.off_z_ctrl.GetValue()
        )
        rotation = (
            self.rot_x_ctrl.GetValue(),
            self.rot_y_ctrl.GetValue(),
            self.rot_z_ctrl.GetValue()
        )
        return offset, rotation

    def _reset_model3d_controls(self):
        self.off_x_ctrl.SetValue(0)
        self.off_y_ctrl.SetValue(0)
        self.off_z_ctrl.SetValue(0)
        self.rot_x_ctrl.SetValue(0)
        self.rot_y_ctrl.SetValue(0)
        self.rot_z_ctrl.SetValue(0)

    def _on_model3d_config_changed(self, event):
        """Update the 3D preview when rotation/offset controls change."""
        offset, rotation = self._get_model3d_values()
        self.config_3d_preview.set_model_transform(rotation, offset)
        event.Skip()

    def _populate_categories(self):
        self.category_combo.Clear()
        categories = self.library_manager.get_categories()
        default_cat = self.library_manager.get_default_category()
        default_idx = 0

        for i, cat in enumerate(categories):
            self.category_combo.Append(cat["name"], cat["id"])
            if cat["id"] == default_cat:
                default_idx = i

        if categories:
            self.category_combo.SetSelection(default_idx)

    def _get_selected_category(self) -> str:
        idx = self.category_combo.GetSelection()
        if idx >= 0:
            return self.category_combo.GetClientData(idx)
        return self.library_manager.get_default_category()

    def _on_add_category(self, event):
        dlg = wx.TextEntryDialog(
            self,
            "Enter a name for the new category:",
            "New Category",
            ""
        )
        dlg.SetBackgroundColour(Theme.BG_ELEVATED)

        if dlg.ShowModal() == wx.ID_OK:
            name = dlg.GetValue().strip()
            if name:
                success, msg = self.library_manager.add_category(name, name)
                if success:
                    self._populate_categories()
                    # Select the new category
                    for i in range(self.category_combo.GetCount()):
                        if self.category_combo.GetString(i) == name:
                            self.category_combo.SetSelection(i)
                            break
                    self._update_status(f"Category '{name}' created", status_type="success")
                else:
                    self._update_status(msg, status_type="error")
        dlg.Destroy()

    def _on_paint_border(self, event):
        dc = wx.PaintDC(self)
        T = Theme
        w, h = self.GetSize()

        dc.SetBrush(wx.TRANSPARENT_BRUSH)
        dc.SetPen(wx.Pen(T.BORDER_SUBTLE, 1))
        dc.DrawRectangle(0, 0, w, h)

        event.Skip()

    def _on_minimize(self):
        self.Iconize(True)

    def _on_close(self):
        self.EndModal(wx.ID_CLOSE)

    def _on_close_btn(self, event):
        self.EndModal(wx.ID_CLOSE)

    def _on_close_evt(self, event):
        self.EndModal(wx.ID_CLOSE)

    def _update_status(self, message: str, status_type: str = "info"):
        self.status_bar.set_status(message, status_type)

    def _update_cache_count(self):
        self.status_bar.set_cache_count(len(self.cache.get_search_history()))

    def _on_search(self, event):
        lcsc_id = self.search_ctrl.GetValue().strip()
        if not lcsc_id:
            self._update_status("Please enter an LCSC part number", status_type="error")
            return

        self._update_status(f"Searching for {lcsc_id}...")
        self.search_btn.Enable(False)
        self.import_btn.Enable(False)
        wx.GetApp().Yield()

        thread = threading.Thread(target=self._do_search, args=(lcsc_id,))
        thread.start()

    def _do_search(self, lcsc_id: str):
        try:
            component = self.cache.get_component(lcsc_id)

            if component is None:
                component = self.client.get_component(lcsc_id)
                if component:
                    self.cache.put_component(component)
                    self.cache.add_search_history(lcsc_id)
                    wx.CallAfter(self._update_cache_count)

            wx.CallAfter(self._on_search_complete, component, lcsc_id)

        except EasyEdaApiError as e:
            wx.CallAfter(self._on_search_error, str(e))
        except Exception as e:
            logger.error(f"Search error: {e}", exc_info=True)
            wx.CallAfter(self._on_search_error, f"Error: {e}")

    def _on_search_complete(self, component: Optional[ComponentInfo], lcsc_id: str):
        self.search_btn.Enable(True)

        if component is None:
            self._update_status(f"Component {lcsc_id} not found", status_type="error")
            self.current_component = None
            self._clear_display()
            return

        self.current_component = component
        self._display_component(component)
        self.import_btn.Enable(True)

        if self.library_manager.is_imported(lcsc_id):
            self._update_status(f"Found {lcsc_id} - Already in library", status_type="info")
        else:
            self._update_status(f"Found {lcsc_id} - Ready to import", status_type="success")

    def _on_search_error(self, error_message: str):
        self.search_btn.Enable(True)
        self._update_status(error_message, status_type="error")

    def _display_component(self, component: ComponentInfo):
        info_items = [
            ("LCSC Part #", component.lcsc_id),
            ("MPN", component.mpn),
            ("Manufacturer", component.manufacturer),
            ("Description", component.description),
            ("Package", component.package),
            ("Category", component.category),
            ("Symbol", "Available" if component.has_symbol() else "Not available"),
            ("Footprint", "Available" if component.has_footprint() else "Not available"),
            ("3D Model", "Available" if component.has_3d_model() else "Not available"),
        ]

        self.info_list.set_items(info_items)

        if component.datasheet_url:
            self.datasheet_link.SetURL(component.datasheet_url)
            self.datasheet_link.Show()
        else:
            self.datasheet_link.Hide()

        self.chk_symbol.Enable(component.has_symbol())
        self.chk_footprint.Enable(component.has_footprint())
        self.chk_3d_model.Enable(component.has_3d_model())

        # Pre-calculate 3D model configuration
        if component.has_3d_model() and component.has_footprint():
            self._calculate_and_set_model3d_values(component)
        else:
            self._reset_model3d_controls()

        self.preview_panel.set_component(component)

        # Update config 3D preview
        if component.has_3d_model():
            self.config_3d_preview.set_model(
                component.model_3d_uuid,
                component.lcsc_id
            )
            offset, rotation = self._get_model3d_values()
            self.config_3d_preview.set_model_transform(rotation, offset)
        else:
            self.config_3d_preview.clear()
        self.Layout()

    def _clear_display(self):
        self.info_list.clear()
        self.datasheet_link.Hide()
        self.preview_panel.clear()
        self.config_3d_preview.clear()
        self._reset_model3d_controls()
        self.Layout()

    def _on_clear(self, event):
        self.search_ctrl.SetValue("")
        self.current_component = None
        self._clear_display()
        self.import_btn.Enable(False)
        self._update_status("Ready. Enter an LCSC part number to search.")

    def _on_import(self, event):
        if not self.current_component:
            return

        import_symbol = self.chk_symbol.GetValue()
        import_footprint = self.chk_footprint.GetValue()
        import_3d_model = self.chk_3d_model.GetValue()
        overwrite = self.chk_overwrite.GetValue()
        category = self._get_selected_category()
        model_offset, model_rotation = self._get_model3d_values()

        if not any([import_symbol, import_footprint, import_3d_model]):
            self._update_status("Select at least one item to import", status_type="error")
            return

        self._update_status(f"Importing {self.current_component.lcsc_id}...")
        self.import_btn.Enable(False)
        wx.GetApp().Yield()

        thread = threading.Thread(
            target=self._do_import,
            args=(self.current_component, import_symbol, import_footprint, import_3d_model,
                  overwrite, category, model_offset, model_rotation)
        )
        thread.start()

    def _do_import(self, component, import_symbol, import_footprint, import_3d_model,
                   overwrite, category, model_offset, model_rotation):
        try:
            success, message = self.library_manager.import_component(
                component,
                import_symbol=import_symbol,
                import_footprint=import_footprint,
                import_3d_model=import_3d_model,
                overwrite=overwrite,
                category=category,
                model_offset=model_offset,
                model_rotation=model_rotation
            )
            wx.CallAfter(self._on_import_complete, success, message)
        except Exception as e:
            logger.error(f"Import error: {e}", exc_info=True)
            wx.CallAfter(self._on_import_complete, False, f"Error: {e}")

    def _on_import_complete(self, success: bool, message: str):
        self.import_btn.Enable(True)
        self._update_status(message, status_type="success" if success else "error")

        if success:
            # Auto-register libraries with KiCad if not already done
            if not self.library_manager.is_registered_with_kicad():
                reg_success, reg_message = self.library_manager.register_libraries_with_kicad()
                if reg_success:
                    wx.MessageBox(
                        f"{message}\n\n{reg_message}",
                        "Import Complete",
                        wx.OK | wx.ICON_INFORMATION,
                        self
                    )
                else:
                    wx.MessageBox(
                        f"{message}\n\n{reg_message}\n\nLibrary path:\n{self.library_manager.get_library_path()}",
                        "Import Complete",
                        wx.OK | wx.ICON_WARNING,
                        self
                    )
            else:
                wx.MessageBox(
                    f"{message}\n\nComponent ready to use in KiCad!",
                    "Import Complete",
                    wx.OK | wx.ICON_INFORMATION,
                    self
                )


def show_dialog(parent=None):
    if wx is None:
        raise ImportError("wxPython is not available")

    dialog = LCSCGrabberDialog(parent)
    dialog.ShowModal()
    dialog.Destroy()
