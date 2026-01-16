#!/usr/bin/env python3
"""
LCSC Grabber - Standalone Launcher

Run this script to launch LCSC Grabber outside of KiCad.
You can also install it as a command with: pip install -e .
"""

import sys
import os

# Add the plugins directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
plugins_dir = os.path.join(script_dir, "plugins")
if plugins_dir not in sys.path:
    sys.path.insert(0, plugins_dir)


def main():
    try:
        import wx
    except ImportError:
        print("Error: wxPython is required but not installed.")
        print("Install it with: pip install wxPython")
        sys.exit(1)

    from lcsc_grabber.gui.main_dialog import LCSCGrabberDialog

    app = wx.App()
    dialog = LCSCGrabberDialog(None)
    dialog.ShowModal()
    dialog.Destroy()
    app.MainLoop()


if __name__ == "__main__":
    main()
