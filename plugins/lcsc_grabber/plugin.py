import os
import sys
import logging


logging.basicConfig(
    level=logging.INFO,
    format='[LCSC Grabber] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


try:
    import pcbnew
    PCBNEW_AVAILABLE = True
except ImportError:
    PCBNEW_AVAILABLE = False
    logger.info("pcbnew not available")

try:
    import eeschema
    EESCHEMA_AVAILABLE = True
except ImportError:
    EESCHEMA_AVAILABLE = False
    logger.info("eeschema not available")

try:
    import wx
    WX_AVAILABLE = True
except ImportError:
    WX_AVAILABLE = False
    logger.warning("wxPython not available")


def get_plugin_path() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def get_icon_path() -> str:
    plugin_path = get_plugin_path()
    icon_path = os.path.join(plugin_path, "..", "..", "resources", "icon.png")
    if os.path.exists(icon_path):
        return icon_path
    icon_path = os.path.join(plugin_path, "icon.png")
    if os.path.exists(icon_path):
        return icon_path
    return ""


class LCSCGrabberPlugin(pcbnew.ActionPlugin if PCBNEW_AVAILABLE else object):

    def defaults(self):
        self.name = "LCSC Grabber"
        self.category = "Component Import"
        self.description = "Import electronic components from LCSC/EasyEDA catalog"
        self.show_toolbar_button = True

        icon_path = get_icon_path()
        if icon_path:
            self.icon_file_name = icon_path

    def Run(self):
        logger.info("LCSC Grabber plugin started")

        if not WX_AVAILABLE:
            logger.error("wxPython is not available")
            if PCBNEW_AVAILABLE:
                import pcbnew
                pcbnew.wxLogError("LCSC Grabber: wxPython is not available")
            return

        try:
            from .gui.main_dialog import LCSCGrabberDialog

            parent = None
            if PCBNEW_AVAILABLE:
                try:
                    parent = wx.GetApp().GetTopWindow()
                except Exception:
                    pass

            dialog = LCSCGrabberDialog(parent)
            dialog.ShowModal()
            dialog.Destroy()

            logger.info("LCSC Grabber plugin finished")

        except Exception as e:
            logger.error(f"Error running LCSC Grabber: {e}", exc_info=True)
            if WX_AVAILABLE:
                wx.MessageBox(
                    f"Error running LCSC Grabber:\n{e}",
                    "LCSC Grabber Error",
                    wx.OK | wx.ICON_ERROR
                )


if PCBNEW_AVAILABLE:
    LCSCGrabberPlugin().register()
    logger.info("LCSC Grabber plugin registered")


def run_standalone():
    if not WX_AVAILABLE:
        print("wxPython is not available. Please install it with: pip install wxPython")
        return

    from .gui.main_dialog import LCSCGrabberDialog

    app = wx.App()
    dialog = LCSCGrabberDialog(None)
    dialog.ShowModal()
    dialog.Destroy()
    app.MainLoop()


if __name__ == "__main__":
    run_standalone()
