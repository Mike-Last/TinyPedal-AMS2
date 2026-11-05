"""
Test Watchlist widget relative rows
"""

import sys
from types import SimpleNamespace

import pytest

sys.path.append(".")
sys.path.append("thirdparty")

from tinypedal.constant import DATA
from tinypedal.widget import watchlist

LAP_TIME = 100.0
PLAYER = 0
DRIVERS = ("Player", "Alice Smith", "Bob", "alice jones", "Carol", "Dave", "Bobby")
# Time gap ahead of player on track (seconds), gap behind is gap ahead - lap time
GAP_AHEAD = {1: 2.0, 2: 10.0, 3: 90.0, 4: 49.0, 5: 51.0, 6: 30.0}
NA = DATA.RELATIVE_NA


@pytest.fixture(autouse=True)
def module_info(monkeypatch):
    """Relative lists as created by module_relative, sorted by reversed time gap"""
    minfo = SimpleNamespace(
        relative=SimpleNamespace(
            relativeAhead=sorted(((gap, idx) for idx, gap in GAP_AHEAD.items()), reverse=True),
            relativeBehind=sorted(((gap - LAP_TIME, idx) for idx, gap in GAP_AHEAD.items()), reverse=True),
        ),
        vehicles=SimpleNamespace(
            dataSet=[SimpleNamespace(driverName=name) for name in DRIVERS],
        ),
    )
    monkeypatch.setattr(watchlist, "minfo", minfo)
    return minfo


def rows(names: str, partial: bool = False, front: int = 3, behind: int = 3) -> list:
    """Watchlist relative rows, without creating the Qt widget"""
    widget = SimpleNamespace(
        watched_names=watchlist.parse_driver_names(names),
        partial_match=partial,
        match_cache={},
        max_veh_front=front,
        max_veh_behind=behind,
    )
    widget.is_watched = lambda name: watchlist.Realtime.is_watched(widget, name)
    return list(watchlist.Realtime.relative_list(widget, PLAYER))


def test_parse_driver_names():
    """Comma separated, trimmed, lowercase, empty names dropped"""
    assert watchlist.parse_driver_names(" Alice Smith , BOB,, ") == ("alice smith", "bob")
    assert watchlist.parse_driver_names("") == ()


def test_exact_match():
    """Exact match ignores case, does not match other names containing it"""
    assert rows("alice smith, BOB") == [NA, (10.0, 2), (2.0, 1), (0.0, PLAYER), NA, NA, NA]


def test_partial_match():
    """Partial match matches any name containing watched name"""
    assert rows("alice", partial=True) == [NA, NA, (2.0, 1), (0.0, PLAYER), (-10.0, 3), NA, NA]
    assert rows("bob", partial=True) == [NA, (30.0, 6), (10.0, 2), (0.0, PLAYER), NA, NA, NA]


def test_nearer_side():
    """Each watched driver is shown once, on the side with the smaller time gap"""
    assert rows("carol, dave") == [NA, NA, (49.0, 4), (0.0, PLAYER), (-49.0, 5), NA, NA]


def test_row_limits():
    """Nearest watched drivers are kept when more are on track than rows"""
    names = "alice smith, bob, alice jones, carol, dave, bobby"
    assert rows(names, front=1, behind=1) == [(2.0, 1), (0.0, PLAYER), (-10.0, 3)]
    assert rows(names, front=2, behind=0) == [(10.0, 2), (2.0, 1), (0.0, PLAYER)]


def test_no_watched_driver():
    """Player row is always shown, so the widget stays visible"""
    assert rows("") == [NA, NA, NA, (0.0, PLAYER), NA, NA, NA]
    assert rows("nobody") == [NA, NA, NA, (0.0, PLAYER), NA, NA, NA]


def test_empty_relative_slots(module_info):
    """Unused relative slots (index -1) are never shown"""
    module_info.relative.relativeAhead.append(NA)
    module_info.relative.relativeBehind.insert(0, NA)
    assert rows("bob") == [NA, NA, (10.0, 2), (0.0, PLAYER), NA, NA, NA]
