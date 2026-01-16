import logging
from typing import Optional, List, Dict, Any

try:
    import wx
except ImportError:
    wx = None

from ..kicad.library_manager import LibraryManager, get_library_manager

logger = logging.getLogger(__name__)


if wx:
    class Theme:
        BG_DARKEST = wx.Colour(22, 22, 26)
        BG_BASE = wx.Colour(28, 28, 32)
        BG_ELEVATED = wx.Colour(38, 38, 44)
        BG_HOVER = wx.Colour(50, 50, 58)

        TEXT_PRIMARY = wx.Colour(210, 210, 215)
        TEXT_SECONDARY = wx.Colour(130, 130, 145)
        TEXT_DISABLED = wx.Colour(80, 80, 92)

        ACCENT = wx.Colour(100, 140, 180)
        ACCENT_HOVER = wx.Colour(120, 160, 200)
        ACCENT_DIM = wx.Colour(80, 110, 140)

        BORDER_SUBTLE = wx.Colour(50, 50, 58)

        SUCCESS = wx.Colour(90, 160, 90)
        ERROR = wx.Colour(180, 80, 80)

        PADDING = 10


class LibraryManagerDialog(wx.Dialog if wx else object):

    def __init__(self, parent, library_manager: LibraryManager = None):
        if wx is None:
            raise ImportError("wxPython is not available")

        super().__init__(
            parent,
            title="Library Manager",
            size=(800, 600),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER
        )

        self.library_manager = library_manager or get_library_manager()
        self.selected_component = None

        self._init_ui()
        self._bind_events()
        self._refresh_component_list()

    def _init_ui(self):
        T = Theme
        PAD = T.PADDING

        self.SetBackgroundColour(T.BG_BASE)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Filter panel
        filter_panel = wx.Panel(self)
        filter_panel.SetBackgroundColour(T.BG_ELEVATED)
        filter_sizer = wx.BoxSizer(wx.HORIZONTAL)

        cat_lbl = wx.StaticText(filter_panel, label="Category:")
        cat_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        filter_sizer.Add(cat_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, PAD)

        self.filter_category = wx.ComboBox(filter_panel, style=wx.CB_READONLY)
        self.filter_category.SetMinSize((150, -1))
        self._populate_category_filter()
        filter_sizer.Add(self.filter_category, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)

        filter_sizer.AddSpacer(20)

        search_lbl = wx.StaticText(filter_panel, label="Search:")
        search_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        filter_sizer.Add(search_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, PAD)

        self.search_ctrl = wx.TextCtrl(filter_panel)
        self.search_ctrl.SetMinSize((200, -1))
        filter_sizer.Add(self.search_ctrl, 1, wx.ALL | wx.EXPAND, 4)

        filter_panel.SetSizer(filter_sizer)
        main_sizer.Add(filter_panel, 0, wx.EXPAND | wx.ALL, 4)

        # Split content
        splitter = wx.SplitterWindow(self, style=wx.SP_LIVE_UPDATE)
        splitter.SetMinimumPaneSize(200)

        # Component list
        list_panel = wx.Panel(splitter)
        list_panel.SetBackgroundColour(T.BG_ELEVATED)
        list_sizer = wx.BoxSizer(wx.VERTICAL)

        list_header = wx.StaticText(list_panel, label="Imported Components")
        list_header.SetForegroundColour(T.ACCENT)
        list_header.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        list_sizer.Add(list_header, 0, wx.ALL, PAD)

        self.component_list = wx.ListCtrl(
            list_panel,
            style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_NONE
        )
        self.component_list.SetBackgroundColour(T.BG_DARKEST)
        self.component_list.SetForegroundColour(T.TEXT_PRIMARY)
        self.component_list.InsertColumn(0, "LCSC ID", width=80)
        self.component_list.InsertColumn(1, "Name", width=150)
        self.component_list.InsertColumn(2, "Category", width=100)
        self.component_list.InsertColumn(3, "MPN", width=120)
        list_sizer.Add(self.component_list, 1, wx.EXPAND | wx.ALL, 4)

        list_panel.SetSizer(list_sizer)

        # Detail panel
        detail_panel = wx.Panel(splitter)
        detail_panel.SetBackgroundColour(T.BG_ELEVATED)
        detail_sizer = wx.BoxSizer(wx.VERTICAL)

        detail_header = wx.StaticText(detail_panel, label="Component Details")
        detail_header.SetForegroundColour(T.ACCENT)
        detail_header.SetFont(wx.Font(10, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        detail_sizer.Add(detail_header, 0, wx.ALL, PAD)

        # Component info
        info_sizer = wx.FlexGridSizer(cols=2, vgap=8, hgap=10)
        info_sizer.AddGrowableCol(1)

        self.detail_lcsc = self._add_detail_row(detail_panel, info_sizer, "LCSC ID:")
        self.detail_name = self._add_detail_row(detail_panel, info_sizer, "Name:")
        self.detail_mpn = self._add_detail_row(detail_panel, info_sizer, "MPN:")
        self.detail_package = self._add_detail_row(detail_panel, info_sizer, "Package:")

        detail_sizer.Add(info_sizer, 0, wx.EXPAND | wx.ALL, PAD)

        # Category change
        cat_change_sizer = wx.BoxSizer(wx.HORIZONTAL)
        cat_change_lbl = wx.StaticText(detail_panel, label="Move to Category:")
        cat_change_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        cat_change_sizer.Add(cat_change_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)

        self.new_category_combo = wx.ComboBox(detail_panel, style=wx.CB_READONLY)
        self._populate_new_category_combo()
        cat_change_sizer.Add(self.new_category_combo, 1, wx.ALL | wx.EXPAND, 4)

        self.move_btn = wx.Button(detail_panel, label="Move")
        self.move_btn.Enable(False)
        cat_change_sizer.Add(self.move_btn, 0, wx.ALL, 4)

        detail_sizer.Add(cat_change_sizer, 0, wx.EXPAND | wx.ALL, PAD)

        # 3D Config
        config_box = wx.StaticBox(detail_panel, label="3D Model Configuration")
        config_box.SetForegroundColour(T.TEXT_SECONDARY)
        config_sizer = wx.StaticBoxSizer(config_box, wx.VERTICAL)

        # Rotation
        rot_sizer = wx.BoxSizer(wx.HORIZONTAL)
        rot_lbl = wx.StaticText(detail_panel, label="Rotation:")
        rot_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        rot_sizer.Add(rot_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)

        rot_x_lbl = wx.StaticText(detail_panel, label="X:")
        rot_x_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        rot_sizer.Add(rot_x_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.rot_x = wx.SpinCtrlDouble(detail_panel, min=-360, max=360, initial=0, inc=1)
        self.rot_x.SetDigits(1)
        self.rot_x.SetMinSize((60, -1))
        rot_sizer.Add(self.rot_x, 0, wx.ALL, 2)

        rot_y_lbl = wx.StaticText(detail_panel, label="Y:")
        rot_y_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        rot_sizer.Add(rot_y_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.rot_y = wx.SpinCtrlDouble(detail_panel, min=-360, max=360, initial=0, inc=1)
        self.rot_y.SetDigits(1)
        self.rot_y.SetMinSize((60, -1))
        rot_sizer.Add(self.rot_y, 0, wx.ALL, 2)

        rot_z_lbl = wx.StaticText(detail_panel, label="Z:")
        rot_z_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        rot_sizer.Add(rot_z_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.rot_z = wx.SpinCtrlDouble(detail_panel, min=-360, max=360, initial=0, inc=1)
        self.rot_z.SetDigits(1)
        self.rot_z.SetMinSize((60, -1))
        rot_sizer.Add(self.rot_z, 0, wx.ALL, 2)

        config_sizer.Add(rot_sizer, 0, wx.EXPAND)

        # Offset
        off_sizer = wx.BoxSizer(wx.HORIZONTAL)
        off_lbl = wx.StaticText(detail_panel, label="Offset (mm):")
        off_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        off_sizer.Add(off_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)

        off_x_lbl = wx.StaticText(detail_panel, label="X:")
        off_x_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        off_sizer.Add(off_x_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.off_x = wx.SpinCtrlDouble(detail_panel, min=-100, max=100, initial=0, inc=0.1)
        self.off_x.SetDigits(2)
        self.off_x.SetMinSize((60, -1))
        off_sizer.Add(self.off_x, 0, wx.ALL, 2)

        off_y_lbl = wx.StaticText(detail_panel, label="Y:")
        off_y_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        off_sizer.Add(off_y_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.off_y = wx.SpinCtrlDouble(detail_panel, min=-100, max=100, initial=0, inc=0.1)
        self.off_y.SetDigits(2)
        self.off_y.SetMinSize((60, -1))
        off_sizer.Add(self.off_y, 0, wx.ALL, 2)

        off_z_lbl = wx.StaticText(detail_panel, label="Z:")
        off_z_lbl.SetForegroundColour(T.TEXT_SECONDARY)
        off_sizer.Add(off_z_lbl, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 4)
        self.off_z = wx.SpinCtrlDouble(detail_panel, min=-100, max=100, initial=0, inc=0.1)
        self.off_z.SetDigits(2)
        self.off_z.SetMinSize((60, -1))
        off_sizer.Add(self.off_z, 0, wx.ALL, 2)

        config_sizer.Add(off_sizer, 0, wx.EXPAND)

        # Apply 3D config button
        self.apply_3d_btn = wx.Button(detail_panel, label="Apply 3D Config")
        self.apply_3d_btn.Enable(False)
        config_sizer.Add(self.apply_3d_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 4)

        detail_sizer.Add(config_sizer, 0, wx.EXPAND | wx.ALL, PAD)

        # Remove button
        self.remove_btn = wx.Button(detail_panel, label="Remove Component")
        self.remove_btn.SetForegroundColour(T.ERROR)
        self.remove_btn.Enable(False)
        detail_sizer.Add(self.remove_btn, 0, wx.ALL | wx.ALIGN_RIGHT, PAD)

        detail_panel.SetSizer(detail_sizer)

        splitter.SplitVertically(list_panel, detail_panel, 400)
        main_sizer.Add(splitter, 1, wx.EXPAND | wx.ALL, 4)

        # Bottom buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        self.close_btn = wx.Button(self, label="Close")
        btn_sizer.Add(self.close_btn, 0, wx.ALL, PAD)

        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 4)

        self.SetSizer(main_sizer)

    def _add_detail_row(self, parent, sizer, label_text):
        T = Theme
        label = wx.StaticText(parent, label=label_text)
        label.SetForegroundColour(T.TEXT_SECONDARY)
        sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)

        value = wx.StaticText(parent, label="-")
        value.SetForegroundColour(T.TEXT_PRIMARY)
        sizer.Add(value, 0, wx.EXPAND)

        return value

    def _bind_events(self):
        self.filter_category.Bind(wx.EVT_COMBOBOX, self._on_filter_change)
        self.search_ctrl.Bind(wx.EVT_TEXT, self._on_filter_change)
        self.component_list.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_component_selected)
        self.move_btn.Bind(wx.EVT_BUTTON, self._on_move_category)
        self.apply_3d_btn.Bind(wx.EVT_BUTTON, self._on_apply_3d_config)
        self.remove_btn.Bind(wx.EVT_BUTTON, self._on_remove_component)
        self.close_btn.Bind(wx.EVT_BUTTON, self._on_close)

    def _populate_category_filter(self):
        self.filter_category.Clear()
        self.filter_category.Append("All Categories", None)
        categories = self.library_manager.get_categories()
        for cat in categories:
            self.filter_category.Append(cat["name"], cat["id"])
        self.filter_category.SetSelection(0)

    def _populate_new_category_combo(self):
        self.new_category_combo.Clear()
        categories = self.library_manager.get_categories()
        for cat in categories:
            self.new_category_combo.Append(cat["name"], cat["id"])
        if categories:
            self.new_category_combo.SetSelection(0)

    def _refresh_component_list(self):
        self.component_list.DeleteAllItems()

        filter_cat = None
        idx = self.filter_category.GetSelection()
        if idx > 0:
            filter_cat = self.filter_category.GetClientData(idx)

        search_text = self.search_ctrl.GetValue().strip().lower()

        components = self.library_manager.get_imported_components_by_category(filter_cat)

        for comp in components:
            if search_text:
                searchable = f"{comp.get('lcsc_id', '')} {comp.get('name', '')} {comp.get('mpn', '')}".lower()
                if search_text not in searchable:
                    continue

            idx = self.component_list.InsertItem(self.component_list.GetItemCount(), comp.get("lcsc_id", ""))
            self.component_list.SetItem(idx, 1, comp.get("name", ""))
            self.component_list.SetItem(idx, 2, comp.get("category", "misc"))
            self.component_list.SetItem(idx, 3, comp.get("mpn", ""))
            self.component_list.SetItemData(idx, idx)

    def _on_filter_change(self, event):
        self._refresh_component_list()
        self._clear_detail()

    def _on_component_selected(self, event):
        idx = event.GetIndex()
        lcsc_id = self.component_list.GetItemText(idx, 0)

        components = self.library_manager.get_imported_components()
        self.selected_component = None
        for comp in components:
            if comp.get("lcsc_id") == lcsc_id:
                self.selected_component = comp
                break

        if self.selected_component:
            self._display_component_detail(self.selected_component)
            self.move_btn.Enable(True)
            self.remove_btn.Enable(True)
            self.apply_3d_btn.Enable(self.selected_component.get("has_3d_model", False))

    def _display_component_detail(self, comp: Dict[str, Any]):
        self.detail_lcsc.SetLabel(comp.get("lcsc_id", "-"))
        self.detail_name.SetLabel(comp.get("name", "-"))
        self.detail_mpn.SetLabel(comp.get("mpn", "-"))
        self.detail_package.SetLabel(comp.get("package", "-"))

        # Set current category in combo
        current_cat = comp.get("category", "misc")
        for i in range(self.new_category_combo.GetCount()):
            if self.new_category_combo.GetClientData(i) == current_cat:
                self.new_category_combo.SetSelection(i)
                break

        # Load 3D config
        config = self.library_manager.get_component_3d_config(comp.get("lcsc_id", ""))
        if config:
            offset = config.get("offset", (0, 0, 0))
            rotation = config.get("rotation", (0, 0, 0))
            self.off_x.SetValue(offset[0])
            self.off_y.SetValue(offset[1])
            self.off_z.SetValue(offset[2])
            self.rot_x.SetValue(rotation[0])
            self.rot_y.SetValue(rotation[1])
            self.rot_z.SetValue(rotation[2])
        else:
            self._reset_3d_controls()

    def _clear_detail(self):
        self.selected_component = None
        self.detail_lcsc.SetLabel("-")
        self.detail_name.SetLabel("-")
        self.detail_mpn.SetLabel("-")
        self.detail_package.SetLabel("-")
        self._reset_3d_controls()
        self.move_btn.Enable(False)
        self.remove_btn.Enable(False)
        self.apply_3d_btn.Enable(False)

    def _reset_3d_controls(self):
        self.off_x.SetValue(0)
        self.off_y.SetValue(0)
        self.off_z.SetValue(0)
        self.rot_x.SetValue(0)
        self.rot_y.SetValue(0)
        self.rot_z.SetValue(0)

    def _on_move_category(self, event):
        if not self.selected_component:
            return

        lcsc_id = self.selected_component.get("lcsc_id", "")
        idx = self.new_category_combo.GetSelection()
        if idx < 0:
            return

        new_cat = self.new_category_combo.GetClientData(idx)
        success, msg = self.library_manager.update_component_category(lcsc_id, new_cat)

        if success:
            wx.MessageBox(msg, "Success", wx.OK | wx.ICON_INFORMATION, self)
            self._refresh_component_list()
        else:
            wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR, self)

    def _on_apply_3d_config(self, event):
        if not self.selected_component:
            return

        lcsc_id = self.selected_component.get("lcsc_id", "")
        offset = (self.off_x.GetValue(), self.off_y.GetValue(), self.off_z.GetValue())
        rotation = (self.rot_x.GetValue(), self.rot_y.GetValue(), self.rot_z.GetValue())

        success, msg = self.library_manager.update_3d_config(lcsc_id, offset=offset, rotation=rotation)

        if success:
            wx.MessageBox(f"3D configuration updated. {msg}", "Success", wx.OK | wx.ICON_INFORMATION, self)
        else:
            wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR, self)

    def _on_remove_component(self, event):
        if not self.selected_component:
            return

        lcsc_id = self.selected_component.get("lcsc_id", "")
        name = self.selected_component.get("name", lcsc_id)

        result = wx.MessageBox(
            f"Are you sure you want to remove '{name}' ({lcsc_id}) from the library?",
            "Confirm Removal",
            wx.YES_NO | wx.ICON_WARNING,
            self
        )

        if result == wx.YES:
            success, msg = self.library_manager.remove_component(lcsc_id)
            if success:
                wx.MessageBox(msg, "Success", wx.OK | wx.ICON_INFORMATION, self)
                self._refresh_component_list()
                self._clear_detail()
            else:
                wx.MessageBox(msg, "Error", wx.OK | wx.ICON_ERROR, self)

    def _on_close(self, event):
        self.EndModal(wx.ID_CLOSE)


def show_library_manager_dialog(parent=None, library_manager=None):
    if wx is None:
        raise ImportError("wxPython is not available")

    dialog = LibraryManagerDialog(parent, library_manager)
    dialog.ShowModal()
    dialog.Destroy()
