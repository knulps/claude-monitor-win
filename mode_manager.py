"""ModeManager: owns Poller + current View, serializes mode switches."""

import os
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

from config import save_mode as cfg_save_mode


class ModeManager:
    def __init__(
        self,
        cfg_path: Path,
        view_factories: Dict[str, Callable],
        poller,
        save_mode: bool,
    ):
        self.cfg_path = Path(cfg_path)
        self.view_factories = view_factories
        self.poller = poller
        self.save_mode = save_mode

        self.current_mode: Optional[str] = None
        self.current_view = None
        self.last_data = None
        self._quit_requested = False
        self._pending_switch: Optional[str] = None

    # -- Lifecycle ---------------------------------------------------------

    def start_initial(self, mode: str):
        if mode not in self.view_factories:
            mode = "overlay"
        self.current_mode = mode
        self.current_view = self.view_factories[mode](self)
        self.current_view.start(self.last_data)

    def run(self):
        """Drive whichever main loop the current view needs.

        Tk-based views: call view.run_mainloop() and re-enter when a switch is requested.
        CLI view: call view.run_mainloop() which blocks on stdin.
        Tray view: pystray's icon.run() blocks.
        """
        while not self._quit_requested:
            run = getattr(self.current_view, "run_mainloop", None)
            if callable(run):
                run()
            # If a switch was queued (the view exited its loop because of stop()), perform it
            if self._pending_switch:
                target = self._pending_switch
                self._pending_switch = None
                self._do_switch(target)
            else:
                # No pending switch; loop exited for quit
                break
        # Cleanup on quit
        if self.current_view:
            self.current_view.stop()
        if self.poller:
            self.poller.stop()

    # -- Poll callback (called from poller thread) -------------------------

    def on_poll_data(self, data):
        self.last_data = data
        # Marshal back to main thread when the view is Tk-based
        view = self.current_view
        if view is None:
            return
        root = getattr(view, "root", None)
        if root is not None:
            try:
                root.after(0, lambda: view.on_update(data))
                return
            except Exception:
                pass
        # CLI/tray views can be updated from any thread; both serialize internally
        view.on_update(data)

    # -- Public requests from views ----------------------------------------

    def request_switch(self, mode: str):
        if mode == self.current_mode or mode not in self.view_factories:
            return
        # CLI → GUI check: CLI mode has no menu, but autohide/overlay/tray → cli needs a console.
        if mode == "cli" and not self._console_attached():
            self._show_no_console_error()
            return
        # Stop view; loop exit triggers _do_switch
        self._pending_switch = mode
        if self.current_view:
            self.current_view.stop()

    def request_refresh(self):
        if self.poller:
            self.poller.trigger()

    def request_quit(self):
        self._quit_requested = True
        if self.current_view:
            self.current_view.stop()

    # -- Internal switch -----------------------------------------------------

    def _do_switch(self, mode: str):
        if self.save_mode:
            try:
                cfg_save_mode(self.cfg_path, mode)
            except Exception as e:
                print(f"[mode save error] {e}")
        # Stop the outgoing view before constructing the next one.
        # View.stop() is idempotent, so a prior stop() from request_switch() is harmless.
        if self.current_view:
            self.current_view.stop()
        self.current_mode = mode
        self.current_view = self.view_factories[mode](self)
        self.current_view.start(self.last_data)

    @staticmethod
    def _console_attached() -> bool:
        try:
            return sys.stdout is not None and sys.stdout.isatty() and os.isatty(1)
        except Exception:
            return False

    def _show_no_console_error(self):
        # Best effort: show a tk messagebox if a Tk view is up
        try:
            import tkinter.messagebox as mb
            from i18n import T
            mb.showerror("CLI mode", T("cli_mode_needs_console"))
        except Exception:
            print("[mode] cli mode needs console")
