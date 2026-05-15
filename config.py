"""Config file loading + targeted line-based saving of INI keys."""

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
    tray_companion: bool
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
            tray_companion=cp.getboolean("ui", "tray_companion", fallback=False),
            tray_popup_position=cp.get("tray", "popup_position", fallback="above"),
            autohide_edge=cp.get("autohide", "edge", fallback="bottom"),
            autohide_peek_pixels=cp.getint("autohide", "peek_pixels", fallback=3),
            autohide_slide_ms=cp.getint("autohide", "slide_ms", fallback=110),
            autohide_hide_delay_ms=cp.getint("autohide", "hide_delay_ms", fallback=1500),
        )


def save_mode(path: Path, mode: str):
    """Persist [ui] mode = <mode>, preserving comments and ordering."""
    _set_ini_key(Path(path), section="ui", key="mode", value=mode)


def _set_ini_key(path: Path, section: str, key: str, value: str):
    """Rewrite [section] key = <value> in-place, preserving comments and ordering.

    configparser's write() would clobber inline comments, so we patch the file
    line-by-line. If [section] or `key` does not exist, append them.
    """
    if not path.exists():
        path.write_text(f"[{section}]\n{key} = {value}\n", encoding="utf-8")
        return

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    in_section = False
    section_seen = False
    key_written = False
    out = []

    section_re = re.compile(r"^\s*\[([^\]]+)\]\s*$")
    key_re = re.compile(rf"^(\s*{re.escape(key)}\s*=[^\S\n]*)(\S*)(.*)$")

    for line in lines:
        sec = section_re.match(line)
        if sec:
            if in_section and not key_written:
                out.append(f"{key} = {value}\n")
                key_written = True
            in_section = sec.group(1).strip().lower() == section.lower()
            if in_section:
                section_seen = True
            out.append(line)
            continue

        if in_section and not key_written:
            m = key_re.match(line)
            if m:
                prefix, _old, tail = m.groups()
                out.append(f"{prefix}{value}{tail}\n" if not tail.endswith("\n") else f"{prefix}{value}{tail}")
                key_written = True
                continue
        out.append(line)

    if in_section and not key_written:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"{key} = {value}\n")
        key_written = True
    elif not section_seen:
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        out.append(f"\n[{section}]\n")
        out.append(f"{key} = {value}\n")

    path.write_text("".join(out), encoding="utf-8")


def save_tray_companion(path: Path, value: bool):
    """Persist [ui] tray_companion = <true|false>."""
    _set_ini_key(Path(path), section="ui", key="tray_companion", value="true" if value else "false")
