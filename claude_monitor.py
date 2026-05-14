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

CFG_PATH = Path(__file__).parent / "config.ini"


def parse_args():
    ap = argparse.ArgumentParser(description="Claude Usage Monitor")
    ap.add_argument("--mode", choices=VALID_MODES, help="Override starting mode (config.ini default if unset)")
    ap.add_argument("--no-save-mode", action="store_true",
                    help="Don't persist mode changes back to config.ini")
    return ap.parse_args()


def main():
    args = parse_args()

    if not CFG_PATH.exists():
        print(f"Missing {CFG_PATH}. Copy config.ini.example and fill in cookies + org_id.")
        sys.exit(1)

    cfg = Config.load(CFG_PATH)
    if not cfg.cookies:
        print("Set 'cookies' under [claude] in config.ini")
        sys.exit(1)
    if not cfg.org_id:
        print("Set 'org_id' under [claude] in config.ini")
        sys.exit(1)

    set_language(cfg.language)
    start_mode = args.mode or cfg.mode

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
