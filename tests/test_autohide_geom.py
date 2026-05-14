from views.autohide import _compute_geoms


def test_right_edge_docks_to_this_monitor_not_primary():
    # Secondary monitor at x 2560..5120 — autohide must dock to 5120, not the primary's 2560.
    mon = (2560, 0, 5120, 1400)
    hidden, shown = _compute_geoms(mon, "right", 230, 178, 3)
    assert hidden == "230x178+5117+1214"   # right(5120) - peek(3); y = bottom(1400) - h(178) - 8
    assert shown == "230x178+4886+1214"    # right(5120) - w(230) - 4


def test_right_edge_primary_monitor():
    mon = (0, 0, 2560, 1400)
    hidden, shown = _compute_geoms(mon, "right", 230, 178, 3)
    assert hidden == "230x178+2557+1214"
    assert shown == "230x178+2326+1214"


def test_left_edge():
    mon = (0, 0, 2560, 1400)
    hidden, shown = _compute_geoms(mon, "left", 230, 178, 3)
    assert hidden == "230x178+-227+1214"   # left(0) - w(230) + peek(3)
    assert shown == "230x178+4+1214"


def test_top_edge():
    mon = (0, 0, 2560, 1400)
    hidden, shown = _compute_geoms(mon, "top", 230, 178, 3)
    assert hidden == "230x178+2314+-175"   # x_band = right(2560) - w(230) - 16; y = top(0) - h(178) + peek(3)
    assert shown == "230x178+2314+4"


def test_bottom_edge():
    mon = (0, 0, 2560, 1400)
    hidden, shown = _compute_geoms(mon, "bottom", 230, 178, 3)
    assert hidden == "230x178+2314+1397"   # bottom(1400) - peek(3)
    assert shown == "230x178+2314+1214"    # bottom(1400) - h(178) - 8
