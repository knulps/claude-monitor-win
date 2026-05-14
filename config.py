"""Config file loading + targeted line-based saving of the `mode` key."""

import configparser
import re
from dataclasses import dataclass
from pathlib import Path

VALID_MODES = ("overlay", "tray", "cli", "autohide")


@dataclass
class Config:
    cookies: str
    org_id: str
    poll_interval: int
    language: str
    mode: str
    tray_popup_position: str
    autohide_edge: str
    autohide_peek_pixels: int
    autohide_slide_ms: int
    autohide_hide_delay_ms: int

    @classmethod
    def load(cls, path):
        cp = configparser.ConfigParser(inline_comment_prefixes=(";",))
        cp.read(path, encoding="utf-8")

        mode = cp.get("ui", "mode", fallback="overlay").strip().lower()
        if mode not in VALID_MODES:
            mode = "overlay"

        return cls(
            cookies=cp.get("claude", "cookies", fallback=""),
            org_id=cp.get("claude", "org_id", fallback=""),
            poll_interval=cp.getint("claude", "poll_interval", fallback=60),
            language=cp.get("ui", "language", fallback="en").strip().lower(),
            mode=mode,
            tray_popup_position=cp.get("tray", "popup_position", fallback="above"),
            autohide_edge=cp.get("autohide", "edge", fallback="right"),
            autohide_peek_pixels=cp.getint("autohide", "peek_pixels", fallback=3),
            autohide_slide_ms=cp.getint("autohide", "slide_ms", fallback=150),
            autohide_hide_delay_ms=cp.getint("autohide", "hide_delay_ms", fallback=1500),
        )


def save_mode(path: Path, mode: str):
    """Rewrite [ui] mode = <mode> in-place, preserving comments and ordering.

    configparser's write() would clobber inline comments, so we patch the file
    line-by-line. If [ui] or `mode` does not exist, append them.
    """
    path = Path(path)
    if not path.exists():
        path.write_text(f"[ui]\nmode = {mode}\n", encoding="utf-8")
        return

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_ui = False
    ui_seen = False
    mode_written = False
    out = []

    section_re = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    mode_re    = re.compile(r"^(\s*mode\s*=[^\S\n]*)(\S*)(.*)$")

    for line in lines:
        sec = section_re.match(line)
        if sec:
            # Leaving [ui] without writing mode -> append before this section
            if in_ui and not mode_written:
                out.append(f"mode = {mode}\n")
                mode_written = True
            in_ui = sec.group(1).strip().lower() == "ui"
            if in_ui:
                ui_seen = True
            out.append(line)
            continue

        if in_ui and not mode_written:
            m = mode_re.match(line)
            if m:
                prefix, _old, tail = m.groups()
                out.append(f"{prefix}{mode}{tail}\n" if not tail.endswith("\n") else f"{prefix}{mode}{tail}")
                mode_written = True
                continue
        out.append(line)

    if in_ui and not mode_written:
        # File ended inside [ui] without a mode key
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"mode = {mode}\n")
        mode_written = True
    elif not ui_seen:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append("\n[ui]\n")
        out.append(f"mode = {mode}\n")

    path.write_text("".join(out), encoding="utf-8")
