__version__ = "1.1.0"
__author__ = "LCSC Grabber Contributors"

from .plugin import LCSCGrabberPlugin


def main():
    """Entry point for standalone launcher."""
    import sys

    try:
        import wx
    except ImportError:
        print("Error: wxPython is required but not installed.")
        print("Install it with: pip install wxPython")
        sys.exit(1)

    from .gui.main_dialog import LCSCGrabberDialog

    app = wx.App()
    dialog = LCSCGrabberDialog(None)
    dialog.ShowModal()
    dialog.Destroy()
    app.MainLoop()
