"""ModeManager: owns Poller + current View, serializes mode switches."""

from pathlib import Path
from typing import Callable, Dict, Optional

from config import save_mode as cfg_save_mode
from views.base import View


class ModeManager:
    def __init__(
        self,
        cfg_path: Path,
        view_factories: Dict[str, Callable],
        poller,
        save_mode: bool,
        companion_factories: Optional[Dict[str, Callable]] = None,
        save_tray_companion: Optional[Callable] = None,
        initial_companion_flag: bool = False,
    ):
        self.cfg_path = Path(cfg_path)
        self.view_factories = view_factories
        self.companion_factories = companion_factories or {}
        self.poller = poller
        self.save_mode = save_mode
        self.save_tray_companion = save_tray_companion
        self.tray_companion = bool(initial_companion_flag)

        self.current_mode: Optional[str] = None
        self.current_view = None
        self.current_companion: Optional[View] = None
        self.last_data = None
        self._quit_requested = False
        self._pending_switch: Optional[str] = None

    # -- Companion helpers -------------------------------------------------

    def _should_show_companion(self) -> bool:
        """Return True only when the companion view should be visible.

        Conditions: tray_companion flag is set AND the active mode is one that
        renders a floating window (overlay / autohide).  Tray and CLI modes
        have no on-screen window, so a companion makes no sense there.
        """
        return self.tray_companion and self.current_mode in ("overlay", "autohide")

    def _sync_companion(self):
        """Idempotent: brings current_companion into agreement with _should_show_companion()."""
        if self._pending_switch is not None:
            # A switch is in flight; _do_switch will call _sync_companion when it lands.
            return
        want = self._should_show_companion()
        if want and self.current_companion is None:
            factory = self.companion_factories.get("tray")
            if factory is None:
                return
            candidate = factory(self)
            try:
                candidate.start(self.last_data)
            except Exception as e:
                print(f"[companion start error] {e}")
                return
            self.current_companion = candidate
        elif not want and self.current_companion is not None:
            try:
                self.current_companion.stop()
            except Exception as e:
                print(f"[companion stop error] {e}")
            self.current_companion = None

    def request_toggle_companion(self, on: bool):
        self.tray_companion = bool(on)
        if self.save_mode and self.save_tray_companion is not None:
            try:
                self.save_tray_companion(self.cfg_path, self.tray_companion)
            except Exception as e:
                print(f"[companion save error] {e}")
        self._sync_companion()

    # -- Lifecycle ---------------------------------------------------------

    def start_initial(self, mode: str):
        if mode not in self.view_factories:
            mode = "overlay"
        self.current_mode = mode
        self.current_view = self.view_factories[mode](self)
        self.current_view.start(self.last_data)
        self._sync_companion()

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
        if self.current_companion:
            try:
                self.current_companion.stop()
            except Exception:
                pass  # Quitting: ignore; log would go to a possibly-dead console.
            self.current_companion = None
        if self.current_view:
            self.current_view.stop()
        if self.poller:
            self.poller.stop()

    # -- Poll callback (called from poller thread) -------------------------

    def on_poll_data(self, data):
        self.last_data = data
        for view in (self.current_view, self.current_companion):
            self._dispatch_to_view(view, data)

    def _dispatch_to_view(self, view, data):
        """Dispatch poll data to a single view (main or companion).

        Tk views are marshalled onto the main thread via root.after.
        The stale-view guard accepts both current_view and current_companion
        so that a view replaced by _do_switch is silently skipped.
        """
        if view is None:
            return
        root = getattr(view, "root", None)
        if root is not None:
            # Tk view: marshal onto the main thread. Guard the callback so a view
            # swapped out between scheduling and running is skipped, and never fall
            # through to a direct cross-thread call if scheduling fails.
            try:
                root.after(
                    0,
                    lambda v=view: v.on_update(data)
                    if v in (self.current_view, self.current_companion)
                    else None,
                )
            except Exception:
                # root was destroyed mid-switch; the next poll reaches the new view.
                pass
            return
        # Non-Tk view (cli/tray), or a Tk view already stopped (root is None).
        # Skip if it is no longer current so a stale view isn't touched.
        if view in (self.current_view, self.current_companion):
            view.on_update(data)

    # -- Public requests from views ----------------------------------------

    def request_switch(self, mode: str):
        if mode == self.current_mode or mode not in self.view_factories:
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

    def request_focus_main_view(self):
        """Ask the current view to bring itself to the foreground.

        Calls view.focus() if the method exists and is callable.
        Any exception from focus() is caught and logged so callers are not disrupted.
        """
        view = self.current_view
        if view is None:
            return
        focus = getattr(view, "focus", None)
        if callable(focus):
            try:
                focus()
            except Exception as e:
                print(f"[focus error] {e}")

    # -- Internal switch -----------------------------------------------------

    def _do_switch(self, mode: str):
        if self.save_mode:
            try:
                cfg_save_mode(self.cfg_path, mode)
            except Exception as e:
                print(f"[mode save error] {e}")
        # Stop the companion first so its borrowed root reference is released
        # before the main view (which owns the root) is destroyed.
        if self.current_companion:
            try:
                self.current_companion.stop()
            except Exception as e:
                print(f"[companion stop error] {e}")
            self.current_companion = None
        # Stop the outgoing view before constructing the next one.
        # View.stop() is idempotent, so a prior stop() from request_switch() is harmless.
        if self.current_view:
            self.current_view.stop()
        self.current_mode = mode
        self.current_view = self.view_factories[mode](self)
        self.current_view.start(self.last_data)
        self._sync_companion()
