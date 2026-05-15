from views.autohide import _compute_geoms


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
