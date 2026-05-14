"""Autohide mode: docks the overlay to a screen edge; slides in on hover."""

import tkinter as tk
from typing import Optional

from i18n import T
from usage_client import UsageData
from views.overlay import OverlayView


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

    def start(self, initial: Optional[UsageData]) -> None:
        super().start(initial)
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
        switch.add_command(label=T("mode_cli"),      command=lambda: self.manager.request_switch("cli"))
        switch.add_command(label=T("mode_autohide"), command=lambda: self.manager.request_switch("autohide"))
        menu.add_cascade(label=T("menu_switch_mode"), menu=switch)
        menu.add_separator()
        menu.add_checkbutton(label=T("menu_force_show"),
                             command=self._toggle_force_show,
                             variable=tk.BooleanVar(value=self._force_show))
        menu.add_command(label=T("menu_refresh"), command=self.manager.request_refresh)
        menu.add_separator()
        menu.add_command(label=T("menu_quit"), command=self.manager.request_quit)
        menu.post(e.x_root, e.y_root)

    def _toggle_force_show(self):
        self._force_show = not self._force_show
        if self._force_show:
            self._slide_in(force=True)

    def _dock_initial(self):
        self._geom_hidden = self._compute_hidden_geom()
        self._geom_shown  = self._compute_shown_geom()
        self.root.geometry(self._geom_hidden)
        self._shown = False

    def _compute_hidden_geom(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if self.EDGE == "right":
            return f"{self.W}x{self.H}+{sw - self.PEEK}+{sh - self.H - 56}"
        if self.EDGE == "left":
            return f"{self.W}x{self.H}+{self.PEEK - self.W}+{sh - self.H - 56}"
        if self.EDGE == "top":
            return f"{self.W}x{self.H}+{sw - self.W - 16}+{self.PEEK - self.H}"
        # bottom
        return f"{self.W}x{self.H}+{sw - self.W - 16}+{sh - self.PEEK}"

    def _compute_shown_geom(self):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        if self.EDGE == "right":
            return f"{self.W}x{self.H}+{sw - self.W - 4}+{sh - self.H - 56}"
        if self.EDGE == "left":
            return f"{self.W}x{self.H}+4+{sh - self.H - 56}"
        if self.EDGE == "top":
            return f"{self.W}x{self.H}+{sw - self.W - 16}+4"
        # bottom
        return f"{self.W}x{self.H}+{sw - self.W - 16}+{sh - self.H - 56}"

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
        # Hidden state — sensitive area is the peek strip
        if self.EDGE == "right":
            sw = self.root.winfo_screenwidth()
            return sw - self.PEEK <= x <= sw and ry <= y <= ry + rh
        if self.EDGE == "left":
            return 0 <= x <= self.PEEK and ry <= y <= ry + rh
        if self.EDGE == "top":
            return rx <= x <= rx + rw and 0 <= y <= self.PEEK
        sh = self.root.winfo_screenheight()
        return rx <= x <= rx + rw and sh - self.PEEK <= y <= sh

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
        # "WxH+X+Y" -> (X, Y)
        try:
            _, pos = geom.split("+", 1)
            x_str, y_str = pos.split("+")
            return int(x_str), int(y_str)
        except Exception:
            return 0, 0
