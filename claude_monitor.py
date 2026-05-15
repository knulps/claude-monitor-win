"""Claude Usage Monitor — entry point.

Loads config, wires up ModeManager + Poller + UsageClient, starts the chosen view.
"""

import argparse
import sys
from pathlib import Path

from config import Config, VALID_MODES
from i18n import set_language
from mode_manager import ModeManager
from poller import Poller
from usage_client import UsageClient
from views.autohide import AutohideView
from views.cli import CLIView
from views.overlay import OverlayView
from views.tray import TrayView

# When frozen by PyInstaller (--onefile), __file__ points into the temporary
# extraction dir; resolve config.ini next to the actual exe instead.
if getattr(sys, "frozen", False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent
CFG_PATH = APP_DIR / "config.ini"


def parse_args():
    ap = argparse.ArgumentParser(description="Claude Usage Monitor")
    ap.add_argument("--mode", choices=VALID_MODES, help="Override starting mode (config.ini default if unset)")
    ap.add_argument("--no-save-mode", action="store_true",
                    help="Don't persist mode changes back to config.ini")
    return ap.parse_args()


def _hide_console_for_frozen_gui(start_mode):
    """A --console build always spawns a console window. When the packaged exe
    runs in a GUI mode, hide it; CLI mode keeps it. No-op when run as a script."""
    if not getattr(sys, "frozen", False) or start_mode == "cli":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)  # SW_HIDE
    except Exception:
        pass


def _show_error(msg, mode):
    """Always print; on a frozen GUI exe, also show a tk messagebox so the user
    actually sees the error (a console window flashes and vanishes on double-click)."""
    print(msg)
    if getattr(sys, "frozen", False) and mode != "cli":
        try:
            import tkinter.messagebox as mb
            mb.showerror("Claude Usage Monitor", msg)
        except Exception:
            pass


def main():
    args = parse_args()

    if not CFG_PATH.exists():
        _show_error(
            f"Missing {CFG_PATH}.\n\nCopy config.ini.example next to the executable "
            f"and fill in cookies + org_id.",
            args.mode,
        )
        sys.exit(1)

    cfg = Config.load(CFG_PATH)
    if not cfg.cookies:
        _show_error("Set 'cookies' under [claude] in config.ini", args.mode)
        sys.exit(1)
    if not cfg.org_id:
        _show_error("Set 'org_id' under [claude] in config.ini", args.mode)
        sys.exit(1)

    set_language(cfg.language)
    start_mode = args.mode or cfg.mode
    _hide_console_for_frozen_gui(start_mode)

    client = UsageClient(org_id=cfg.org_id, cookies=cfg.cookies)
    mgr = ModeManager(
        cfg_path=CFG_PATH,
        view_factories={
            "overlay":  OverlayView,
            "tray":     TrayView,
            "cli":      CLIView,
            "autohide": AutohideView,
        },
        poller=None,  # set below
        save_mode=not args.no_save_mode,
    )
    # Expose cfg to views that need it (Autohide reads autohide_* fields)
    mgr.config = cfg

    poller = Poller(client, interval=cfg.poll_interval, on_data=mgr.on_poll_data)
    mgr.poller = poller

    poller.start()
    mgr.start_initial(start_mode)
    try:
        mgr.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
