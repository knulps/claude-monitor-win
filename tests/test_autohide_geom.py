from views.autohide import _compute_geoms, _in_zone


def test_right_edge_docks_to_this_monitor_not_primary():
    # Secondary monitor at x 2560..5120 — autohide must dock to 5120, not the primary's 2560.
    mon = (2560, 0, 5120, 1400)
    hidden, shown = _compute_geoms(mon, mon, "right", 230, 178, 3)
    assert hidden == "230x178+5117+1214"   # full.right(5120) - peek(3); y = work.bottom(1400) - h(178) - 8
    assert shown == "230x178+4886+1214"    # work.right(5120) - w(230) - 4


def test_right_edge_primary_monitor():
    mon = (0, 0, 2560, 1400)
    hidden, shown = _compute_geoms(mon, mon, "right", 230, 178, 3)
    assert hidden == "230x178+2557+1214"
    assert shown == "230x178+2326+1214"


def test_left_edge():
    mon = (0, 0, 2560, 1400)
    hidden, shown = _compute_geoms(mon, mon, "left", 230, 178, 3)
    assert hidden == "230x178+-227+1214"   # full.left(0) - w(230) + peek(3)
    assert shown == "230x178+4+1214"


def test_top_edge():
    mon = (0, 0, 2560, 1400)
    hidden, shown = _compute_geoms(mon, mon, "top", 230, 178, 3)
    assert hidden == "230x178+2314+-175"   # x_band = work.right(2560) - w(230) - 16; y = full.top(0) - h(178) + peek(3)
    assert shown == "230x178+2314+4"


def test_bottom_edge_hides_past_taskbar():
    # Work area excludes a 48px bottom taskbar; full monitor includes it.
    work = (0, 0, 2560, 1392)
    full = (0, 0, 2560, 1440)
    hidden, shown = _compute_geoms(work, full, "bottom", 230, 178, 3)
    # hidden slides to the FULL monitor bottom (past the taskbar), only peek visible
    assert hidden == "230x178+2314+1437"   # full.bottom(1440) - peek(3)
    # shown sits within the WORK area so it doesn't cover the taskbar
    assert shown == "230x178+2314+1206"    # work.bottom(1392) - h(178) - 8


def test_right_edge_with_right_taskbar():
    # Taskbar on the right edge (48px): docking edge uses full, band uses work.
    work = (0, 0, 2512, 1440)
    full = (0, 0, 2560, 1440)
    hidden, shown = _compute_geoms(work, full, "right", 230, 178, 3)
    assert hidden == "230x178+2557+1254"   # full.right(2560) - peek(3); y = work.bottom(1440) - 178 - 8
    assert shown == "230x178+2278+1254"    # work.right(2512) - w(230) - 4


def test_in_zone_shown_bottom_includes_peek_strip():
    """Regression: edge=bottom shown — window sits above the taskbar but the trigger
    peek strip is at the screen bottom. The active zone must span window->screen edge,
    or the cursor held on the strip flickers the window hide/show."""
    full = (0, 0, 2560, 1440)         # fb = 1440 (physical screen bottom)
    win = (2314, 1206, 230, 178)      # shown position (above the taskbar)
    assert _in_zone(True, "bottom", win, full, 3, 2400, 1439) is True   # on the bottom strip -> still inside
    assert _in_zone(True, "bottom", win, full, 3, 2400, 1250) is True   # on the window itself
    assert _in_zone(True, "bottom", win, full, 3, 2400, 1100) is False  # above the window -> outside
    assert _in_zone(True, "bottom", win, full, 3, 2000, 1250) is False  # left of the window column -> outside


def test_in_zone_hidden_bottom_peek_strip():
    full = (0, 0, 2560, 1440)
    win = (2314, 1437, 230, 178)      # hidden position: ry = fb - peek
    assert _in_zone(False, "bottom", win, full, 3, 2400, 1439) is True   # on the strip
    assert _in_zone(False, "bottom", win, full, 3, 2400, 1400) is False  # above the strip


def test_in_zone_shown_right_includes_peek_strip():
    """Same flicker guard for the right edge."""
    full = (0, 0, 2560, 1440)         # fr = 2560
    win = (2326, 1206, 230, 178)      # shown position
    assert _in_zone(True, "right", win, full, 3, 2559, 1250) is True    # on the right strip -> inside
    assert _in_zone(True, "right", win, full, 3, 2400, 1100) is False   # above the window row -> outside
