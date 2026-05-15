"""Autohide mode: docks the overlay to a screen edge; slides in on hover."""

import ctypes
from ctypes import wintypes
import tkinter as tk
from typing import Optional

from i18n import T
from usage_client import UsageData
from views.overlay import OverlayView


def _compute_geoms(work, full, edge, w, h, peek):
    """Return (hidden_geom, shown_geom) Tk geometry strings for a w x h window
    docked to `edge`.

    `work` and `full` are (left, top, right, bottom) tuples for the monitor's
    work area and full physical bounds. The docking edge uses `full` so the
    hidden window slides past the taskbar / off-screen; the perpendicular band
    and the shown position use `work` so a shown window never covers the taskbar.

    Pure function so the multi-monitor / taskbar math can be unit-tested.
    """
    wl, wt, wr, wb = work
    fl, ft, fr, fb = full
    y_band = wb - h - 8    # vertical placement for left/right edges
    x_band = wr - w - 16   # horizontal placement for top/bottom edges
    if edge == "left":
        return (f"{w}x{h}+{fl - w + peek}+{y_band}",
                f"{w}x{h}+{wl + 4}+{y_band}")
    if edge == "top":
        return (f"{w}x{h}+{x_band}+{ft - h + peek}",
                f"{w}x{h}+{x_band}+{wt + 4}")
    if edge == "bottom":
        return (f"{w}x{h}+{x_band}+{fb - peek}",
                f"{w}x{h}+{x_band}+{wb - h - 8}")
    # right (default)
    return (f"{w}x{h}+{fr - peek}+{y_band}",
            f"{w}x{h}+{wr - w - 4}+{y_band}")


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


class AutohideView(OverlayView):
    """Overlay that hides to a screen edge, peeking PEEK px until mouse hover."""

    EDGE = "right"
    PEEK = 3
    SLIDE_MS = 150
    HIDE_DELAY_MS = 1500
    SLIDE_STEPS = 10

    def __init__(self, manager):
        super().__init__(manager)
        # Read config off the manager so behavior is data-driven
        cfg = getattr(manager, "config", None)
        if cfg is not None:
            self.EDGE = cfg.autohide_edge
            self.PEEK = cfg.autohide_peek_pixels
            self.SLIDE_MS = cfg.autohide_slide_ms
            self.HIDE_DELAY_MS = cfg.autohide_hide_delay_ms
        self._shown = False
        self._hover = False
        self._force_show = False
        self._hide_after_id = None
        self._poll_after_id = None
        self._work_rect = None   # work area of the monitor we docked to
        self._full_rect = None   # full physical bounds of that monitor
        # Created in start() once self.root exists; reused across _show_menu calls
        # so it isn't garbage-collected (which would unset its Tcl variable).
        self._force_show_var = None

    def start(self, initial: Optional[UsageData]) -> None:
        super().start(initial)
        self._force_show_var = tk.BooleanVar(self.root, value=self._force_show)
        # Dock immediately, before hover polling starts, so _slide_in/_slide_out
        # always have _geom_hidden/_geom_shown available.
        self._dock_initial()
        self._poll_hover()

    def stop(self) -> None:
        if self._hide_after_id and self.root:
            try:
                self.root.after_cancel(self._hide_after_id)
            except Exception:
                pass
            self._hide_after_id = None
        if self._poll_after_id and self.root:
            try:
                self.root.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None
        super().stop()

    # Override the right-click menu to add "Force show"
    def _show_menu(self, e):
        menu = tk.Menu(self.root, tearoff=0, bg="#2C2C2E", fg="white",
                       activebackground="#3A3A3C", activeforeground="white")
        switch = tk.Menu(menu, tearoff=0, bg="#2C2C2E", fg="white",
                         activebackground="#3A3A3C", activeforeground="white")
        switch.add_command(label=T("mode_overlay"),  command=lambda: self.manager.request_switch("overlay"))
        switch.add_command(label=T("mode_tray"),     command=lambda: self.manager.request_switch("tray"))
        switch.add_command(label=T("mode_autohide"), command=lambda: self.manager.request_switch("autohide"))
        menu.add_cascade(label=T("menu_switch_mode"), menu=switch)
        menu.add_separator()
        self._force_show_var.set(self._force_show)
        menu.add_checkbutton(label=T("menu_force_show"),
                             command=self._toggle_force_show,
                             variable=self._force_show_var)
        menu.add_command(label=T("menu_refresh"), command=self.manager.request_refresh)
        menu.add_separator()
        menu.add_command(label=T("menu_quit"), command=self.manager.request_quit)
        menu.post(e.x_root, e.y_root)

    def _toggle_force_show(self):
        self._force_show = not self._force_show
        if self._force_show:
            self._slide_in(force=True)
        elif not self._hover and self._shown:
            # Force show turned off while the cursor is away — schedule the hide
            # the hover state machine would otherwise miss (it only acts on edges).
            self._schedule_hide()

    def _dock_initial(self):
        self._work_rect, self._full_rect = self._current_monitor_rects()
        self._geom_hidden, self._geom_shown = _compute_geoms(
            self._work_rect, self._full_rect, self.EDGE, self.W, self.H, self.PEEK)
        self.root.geometry(self._geom_hidden)
        self._shown = False

    def _current_monitor_rects(self):
        """Return (work_rect, full_rect) of the monitor the window currently sits on.

        Uses the window's center point; falls back to the primary monitor.
        """
        try:
            cx = self.root.winfo_rootx() + self.W // 2
            cy = self.root.winfo_rooty() + self.H // 2
            user32 = ctypes.windll.user32
            user32.MonitorFromPoint.restype = wintypes.HMONITOR
            user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user32.GetMonitorInfoW.restype = wintypes.BOOL
            user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.c_void_p]
            hmon = user32.MonitorFromPoint(wintypes.POINT(cx, cy), 2)  # MONITOR_DEFAULTTONEAREST
            mi = _MONITORINFO()
            mi.cbSize = ctypes.sizeof(_MONITORINFO)
            if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                w = mi.rcWork
                m = mi.rcMonitor
                return ((w.left, w.top, w.right, w.bottom),
                        (m.left, m.top, m.right, m.bottom))
        except Exception:
            pass
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        return ((0, 0, sw, sh), (0, 0, sw, sh))

    def _poll_hover(self):
        if not self.root:
            return
        try:
            x, y = self.root.winfo_pointerxy()
        except Exception:
            self._poll_after_id = self.root.after(200, self._poll_hover)
            return
        in_zone = self._cursor_in_active_zone(x, y)
        if in_zone and not self._hover:
            self._hover = True
            if not self._shown:
                self._slide_in()
        elif not in_zone and self._hover:
            self._hover = False
            if self._shown and not self._force_show:
                self._schedule_hide()
        self._poll_after_id = self.root.after(150, self._poll_hover)

    def _cursor_in_active_zone(self, x, y):
        rx = self.root.winfo_rootx()
        ry = self.root.winfo_rooty()
        rw = self.W
        rh = self.H
        if self._shown:
            return rx <= x <= rx + rw and ry <= y <= ry + rh
        # Hidden state — the peek strip sits on the FULL monitor edge.
        fl, ft, fr, fb = self._full_rect or (0, 0, rx + rw, ry + rh)
        if self.EDGE == "right":
            return fr - self.PEEK <= x <= fr and ry <= y <= ry + rh
        if self.EDGE == "left":
            return fl <= x <= fl + self.PEEK and ry <= y <= ry + rh
        if self.EDGE == "top":
            return rx <= x <= rx + rw and ft <= y <= ft + self.PEEK
        return rx <= x <= rx + rw and fb - self.PEEK <= y <= fb

    def _slide_in(self, force=False):
        if self._shown and not force:
            return
        self._cancel_hide()
        self._animate(self._geom_hidden, self._geom_shown)
        self._shown = True

    def _slide_out(self):
        if not self._shown or self._force_show:
            return
        self._animate(self._geom_shown, self._geom_hidden)
        self._shown = False

    def _schedule_hide(self):
        self._cancel_hide()
        self._hide_after_id = self.root.after(self.HIDE_DELAY_MS, self._slide_out)

    def _cancel_hide(self):
        if self._hide_after_id:
            try:
                self.root.after_cancel(self._hide_after_id)
            except Exception:
                pass
            self._hide_after_id = None

    def _animate(self, frm, to):
        fx, fy = self._parse_pos(frm)
        tx, ty = self._parse_pos(to)
        step_ms = max(1, self.SLIDE_MS // self.SLIDE_STEPS)

        def step(i):
            if not self.root:
                return
            frac = i / self.SLIDE_STEPS
            x = int(fx + (tx - fx) * frac)
            y = int(fy + (ty - fy) * frac)
            self.root.geometry(f"{self.W}x{self.H}+{x}+{y}")
            if i < self.SLIDE_STEPS:
                self.root.after(step_ms, lambda: step(i + 1))

        step(1)

    @staticmethod
    def _parse_pos(geom):
        # "WxH+X+Y" -> (X, Y); handles negative coords like "WxH+-227+0"
        try:
            _, pos = geom.split("+", 1)
            x_str, y_str = pos.split("+")
            return int(x_str), int(y_str)
        except Exception:
            return 0, 0
