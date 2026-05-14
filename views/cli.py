"""CLI mode: single-line ANSI output redrawn in place; 'q' + Enter to quit."""

import sys
import threading
from datetime import datetime
from typing import Optional

from i18n import T
from usage_client import UsageData
from views.base import View
from views.overlay import time_until

RESET   = "\x1b[0m"
GREEN   = "\x1b[32m"
YELLOW  = "\x1b[33m"
RED     = "\x1b[31m"
DIM     = "\x1b[90m"


def color_for(pct):
    if pct is None:
        return DIM
    if pct < 60:
        return GREEN
    if pct < 85:
        return YELLOW
    return RED


def render_line(data: Optional[UsageData]) -> str:
    if not data:
        return "loading..."
    parts = [
        f"5h {color_for(data.five_hour_pct)}{_pct(data.five_hour_pct)}{RESET}",
        f"7d {color_for(data.seven_day_pct)}{_pct(data.seven_day_pct)}{RESET}",
        f"Sonnet {color_for(data.seven_day_sonnet_pct)}{_pct(data.seven_day_sonnet_pct)}{RESET}",
        f"Extra {(data.extra_used or 0):.0f}/{data.extra_limit or 0}",
        f"{T('reset')} {time_until(data.five_hour_resets_at)}",
        f"[{datetime.now().strftime('%H:%M')}]",
    ]
    return " │ ".join(parts)


def _pct(pct):
    return f"{int(pct):>3}%" if pct is not None else "  —%"


class CLIView(View):
    def __init__(self, manager):
        super().__init__(manager)
        self._stop = threading.Event()
        self._last: Optional[UsageData] = None
        self._lock = threading.Lock()
        self._input_thread: Optional[threading.Thread] = None

    def start(self, initial: Optional[UsageData]) -> None:
        # Enable ANSI on Windows 10+ conhost
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                pass
        self._last = initial
        print(f"{DIM}{T('cli_quit_hint')}{RESET}")
        self._redraw()

    def run_mainloop(self):
        # Block on stdin for 'q' + Enter
        self._input_thread = threading.Thread(target=self._stdin_loop, daemon=True)
        self._input_thread.start()
        self._stop.wait()
        # Clean line and add newline before exit
        sys.stdout.write("\r\x1b[K\n")
        sys.stdout.flush()

    def stop(self) -> None:
        self._stop.set()

    def on_update(self, data: UsageData) -> None:
        self._last = data
        self._redraw()

    def _redraw(self):
        with self._lock:
            sys.stdout.write("\r\x1b[K" + render_line(self._last))
            sys.stdout.flush()

    def _stdin_loop(self):
        try:
            while not self._stop.is_set():
                line = sys.stdin.readline()
                if not line:
                    break
                if line.strip().lower() == "q":
                    self.manager.request_quit()
                    return
        except Exception:
            pass
