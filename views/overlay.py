"""Overlay mode: the original floating, always-on-top window."""

import tkinter as tk
from datetime import datetime, timezone
from typing import Optional

from i18n import T
from usage_client import UsageData
from views.base import View

BG  = "#1C1C1E"
DIM = "#AEAEB2"
SEP = "#2C2C2E"


def pct_color(pct):
    if pct is None:
        return "#636366"
    if pct < 60:
        return "#30D158"
    if pct < 85:
        return "#FFD60A"
    return "#FF453A"


def time_until(iso_str):
    if not iso_str:
        return "?"
    try:
        reset = datetime.fromisoformat(iso_str)
        now   = datetime.now(timezone.utc)
        secs  = int((reset - now).total_seconds())
        if secs <= 0:
            return T("resetting_soon")
        d, r1 = divmod(secs, 86400)
        h, r2 = divmod(r1, 3600)
        m      = r2 // 60
        if d:
            return f"{d}d {h}h"
        return f"{h}h {m:02d}m" if h else f"{m}m"
    except Exception:
        return "?"


class OverlayView(View):
    W, H = 230, 178

    def __init__(self, manager):
        super().__init__(manager)
        self.root = None
        self._tick_after_id = None
        self._last = None

    def start(self, initial: Optional[UsageData]) -> None:
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.90)
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"{self.W}x{self.H}+{sw - self.W - 16}+{sh - self.H - 56}")

        self._build_ui()
        self._bind_drag()
        self._bind_menu()

        if initial:
            self.on_update(initial)

        self._tick()
        # Note: caller (ModeManager) drives mainloop via run_mainloop()

    def run_mainloop(self):
        if self.root:
            self.root.mainloop()

    def stop(self) -> None:
        if self._tick_after_id and self.root:
            try:
                self.root.after_cancel(self._tick_after_id)
            except Exception:
                pass
            self._tick_after_id = None
        if self.root:
            try:
                self.root.destroy()
            except Exception:
                pass
            self.root = None

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=10, pady=(8, 2))
        tk.Label(hdr, text="Claude", bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(side="left")
        self.lbl_updated = tk.Label(hdr, text="", bg=BG, fg=DIM, font=("Segoe UI", 8))
        self.lbl_updated.pack(side="right")

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x", padx=10)

        row5 = tk.Frame(self.root, bg=BG)
        row5.pack(fill="x", padx=10, pady=(6, 0))
        tk.Label(row5, text=T("session_5h"), bg=BG, fg=DIM, font=("Segoe UI", 8)).pack(side="left", anchor="s", pady=(0, 4))
        self.lbl_5h_reset = tk.Label(row5, text="", bg=BG, fg=DIM, font=("Segoe UI", 8))
        self.lbl_5h_reset.pack(side="right", anchor="s", pady=(0, 4))

        self.lbl_5h = tk.Label(self.root, text="—", bg=BG, fg="#30D158", font=("Segoe UI", 32, "bold"))
        self.lbl_5h.pack(anchor="w", padx=10)

        outer = tk.Frame(self.root, bg="#3A3A3C", height=5)
        outer.pack(fill="x", padx=10, pady=(0, 6))
        outer.pack_propagate(False)
        self.bar = tk.Frame(outer, bg="#30D158", height=5)
        self.bar.place(x=0, y=0, relheight=1, relwidth=0)

        tk.Frame(self.root, bg=SEP, height=1).pack(fill="x", padx=10)

        row7 = tk.Frame(self.root, bg=BG)
        row7.pack(fill="x", padx=10, pady=(5, 2))
        self.lbl_7d     = tk.Label(row7, text=f"{T('label_7d')}  —%", bg=BG, fg="#EBEBF5", font=("Segoe UI", 10))
        self.lbl_7d.pack(side="left")
        self.lbl_sonnet = tk.Label(row7, text="Sonnet  —%", bg=BG, fg="#EBEBF5", font=("Segoe UI", 10))
        self.lbl_sonnet.pack(side="right")

        self.lbl_7d_reset = tk.Label(self.root, text="", bg=BG, fg=DIM, font=("Segoe UI", 8), anchor="w")
        self.lbl_7d_reset.pack(fill="x", padx=10, pady=(0, 2))

        self.lbl_extra = tk.Label(self.root, text="Extra: —", bg=BG, fg=DIM, font=("Segoe UI", 8), anchor="w")
        self.lbl_extra.pack(fill="x", padx=10, pady=(0, 6))

    def on_update(self, data: UsageData) -> None:
        self._last = data
        c5 = pct_color(data.five_hour_pct)
        self.lbl_5h.config(text=f"{data.five_hour_pct:.0f}%" if data.five_hour_pct is not None else "—", fg=c5)
        self.bar.config(bg=c5)
        self.bar.place(relwidth=(data.five_hour_pct or 0) / 100)
        self.lbl_5h_reset.config(text=f"{T('reset')} {time_until(data.five_hour_resets_at)}")

        self.lbl_7d.config(
            text=f"{T('label_7d')}  {data.seven_day_pct:.0f}%" if data.seven_day_pct is not None else f"{T('label_7d')}  —%",
            fg=pct_color(data.seven_day_pct),
        )
        self.lbl_7d_reset.config(text=f"{T('reset_7d')} {time_until(data.seven_day_resets_at)}")

        self.lbl_sonnet.config(
            text=f"Sonnet  {data.seven_day_sonnet_pct:.0f}%" if data.seven_day_sonnet_pct is not None else "Sonnet  —",
            fg=pct_color(data.seven_day_sonnet_pct),
        )

        self.lbl_extra.config(
            text=f"Extra: {(data.extra_used or 0):.0f}/{data.extra_limit or 0} ({(data.extra_pct or 0):.1f}%)"
        )

        now = datetime.now().strftime("%H:%M")
        self.lbl_updated.config(text=now)

    def _tick(self):
        if not self.root:
            return
        self.root.attributes("-topmost", False)
        self.root.attributes("-topmost", True)
        self.root.lift()
        if self._last:
            self.lbl_5h_reset.config(text=f"{T('reset')} {time_until(self._last.five_hour_resets_at)}")
            self.lbl_7d_reset.config(text=f"{T('reset_7d')} {time_until(self._last.seven_day_resets_at)}")
        self._tick_after_id = self.root.after(10_000, self._tick)

    def _bind_drag(self):
        self.root.bind("<Button-1>",  self._drag_start)
        self.root.bind("<B1-Motion>", self._drag_move)

    def _drag_start(self, e):
        self._dx = e.x
        self._dy = e.y

    def _drag_move(self, e):
        x = self.root.winfo_x() + e.x - self._dx
        y = self.root.winfo_y() + e.y - self._dy
        self.root.geometry(f"+{x}+{y}")

    def _bind_menu(self):
        self.root.bind("<Button-3>", self._show_menu)

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
        menu.add_command(label=T("menu_refresh"), command=self.manager.request_refresh)
        menu.add_separator()
        menu.add_command(label=T("menu_quit"), command=self.manager.request_quit)
        menu.post(e.x_root, e.y_root)
