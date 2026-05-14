"""Tray mode: pystray icon with color+number, hover tooltip, left-click popup."""

import threading
import tkinter as tk
from datetime import datetime
from typing import Optional

import pystray
from PIL import Image, ImageDraw, ImageFont

from i18n import T
from usage_client import UsageData
from views.base import View
from views.overlay import pct_color, time_until

ICON_SIZE = 64  # Rendered at 64 for clarity; Windows downsizes to 16/24/32


def _font(size: int):
    try:
        return ImageFont.truetype("seguibl.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("arialbd.ttf", size)
        except Exception:
            return ImageFont.load_default()


def make_icon_image(pct: Optional[float]) -> Image.Image:
    """Solid color background with the percentage drawn on top."""
    color = pct_color(pct)
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), color)
    draw = ImageDraw.Draw(img)
    if pct is None:
        text = "—"
    elif pct >= 100:
        text = "!!"
    else:
        text = f"{int(pct)}"
    font_size = 40 if len(text) == 1 else 32
    font = _font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((ICON_SIZE - tw) / 2 - bbox[0], (ICON_SIZE - th) / 2 - bbox[1]),
              text, fill="white", font=font)
    return img


def make_tooltip(data: Optional[UsageData]) -> str:
    if not data:
        return "Claude Usage  (loading)"
    now = datetime.now().strftime("%H:%M")
    return (
        f"Claude Usage  {now}\n"
        f"5h session {fmt(data.five_hour_pct)}  · Reset {time_until(data.five_hour_resets_at)}\n"
        f"7d         {fmt(data.seven_day_pct)}  · Reset {time_until(data.seven_day_resets_at)}\n"
        f"Sonnet     {fmt(data.seven_day_sonnet_pct)}\n"
        f"Extra      {data.extra_used:.0f}/{data.extra_limit} ({data.extra_pct:.1f}%)"
    )


def fmt(pct):
    return f"{int(pct):>3}%" if pct is not None else "  —%"


class TrayView(View):
    def __init__(self, manager):
        super().__init__(manager)
        self.icon: Optional[pystray.Icon] = None
        self._popup: Optional[tk.Toplevel] = None
        self._last: Optional[UsageData] = None
        self._tk_root: Optional[tk.Tk] = None
        self._stop = threading.Event()

    # ModeManager calls start() on main thread.
    def start(self, initial: Optional[UsageData]) -> None:
        self._last = initial
        # Create a hidden Tk root so we can spawn popup Toplevels later.
        self._tk_root = tk.Tk()
        self._tk_root.withdraw()
        self.icon = pystray.Icon(
            "claude_monitor",
            icon=make_icon_image(initial.five_hour_pct if initial else None),
            title=make_tooltip(initial),
            menu=self._build_menu(),
        )
        # pystray's run() blocks; run in a thread, and pump Tk via run_mainloop()
        threading.Thread(target=self.icon.run, daemon=True).start()

    def run_mainloop(self):
        # Drive Tk so popup Toplevels stay responsive; exit when stopped.
        # ~20Hz pump is enough — popup is rare and tooltip updates use after(0).
        while not self._stop.is_set() and self._tk_root is not None:
            try:
                self._tk_root.update()
            except tk.TclError:
                break
            self._stop.wait(0.05)

    def stop(self) -> None:
        self._stop.set()
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
        if self._tk_root is not None:
            try:
                self._tk_root.destroy()
            except Exception:
                pass
            self._tk_root = None

    def on_update(self, data: UsageData) -> None:
        self._last = data
        if self.icon:
            try:
                self.icon.icon = make_icon_image(data.five_hour_pct)
                self.icon.title = make_tooltip(data)
            except Exception as e:
                print(f"[tray update error] {e}")
        # Refresh popup if it's open
        if self._popup is not None and self._tk_root is not None:
            self._tk_root.after(0, self._refresh_popup)

    # -- Menu / interactions ------------------------------------------------

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(T("menu_switch_mode"), pystray.Menu(
                pystray.MenuItem(T("mode_overlay"),  lambda: self.manager.request_switch("overlay")),
                pystray.MenuItem(T("mode_tray"),     lambda: None, enabled=False),
                pystray.MenuItem(T("mode_cli"),      lambda: self.manager.request_switch("cli")),
                pystray.MenuItem(T("mode_autohide"), lambda: self.manager.request_switch("autohide")),
            )),
            pystray.MenuItem(T("menu_refresh"), lambda: self.manager.request_refresh()),
            pystray.MenuItem(T("menu_quit"),    lambda: self.manager.request_quit()),
            pystray.MenuItem("show", self._on_left_click, default=True, visible=False),
        )

    def _on_left_click(self, icon, item):
        # pystray fires this on left-click of the tray icon
        if self._tk_root is None:
            return
        self._tk_root.after(0, self._toggle_popup)

    def _toggle_popup(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
            return
        self._open_popup()

    def _open_popup(self):
        if self._tk_root is None:
            return
        p = tk.Toplevel(self._tk_root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg="#1C1C1E")
        p.geometry("240x170")
        # Place near bottom-right corner (above tray)
        sw = p.winfo_screenwidth()
        sh = p.winfo_screenheight()
        p.geometry(f"+{sw - 260}+{sh - 230}")

        body = tk.Label(p, text=make_tooltip(self._last), bg="#1C1C1E", fg="#EBEBF5",
                        font=("Segoe UI", 10), justify="left", anchor="nw")
        body.pack(fill="both", expand=True, padx=12, pady=10)

        def close(_=None):
            try:
                p.destroy()
            except Exception:
                pass
            self._popup = None

        p.bind("<FocusOut>", close)
        p.bind("<Button-1>", close)
        p.focus_force()
        self._popup = p

    def _refresh_popup(self):
        if self._popup is None:
            return
        try:
            for child in self._popup.winfo_children():
                if isinstance(child, tk.Label):
                    child.config(text=make_tooltip(self._last))
                    break
        except Exception:
            pass
