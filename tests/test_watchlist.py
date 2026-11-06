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


def rows(names: str, partial: bool = False, show_player: bool = True) -> list:
    """Watchlist relative rows, without creating the Qt widget"""
    widget = SimpleNamespace(
        wcfg={"watched_driver_names": names, "show_player": show_player},
        partial_match=partial,
        match_cache={},
    )
    widget.veh_range = watchlist.Realtime.row_count(widget, 7)
    widget.is_watched = lambda name: watchlist.Realtime.is_watched(widget, name)
    result = list(watchlist.Realtime.relative_list(widget, PLAYER))
    rows.present = widget.watched_present
    return result


def test_parse_driver_names():
    """Comma separated, trimmed, lowercase, empty names dropped"""
    assert watchlist.parse_driver_names(" Alice Smith , BOB,, ") == ("alice smith", "bob")
    assert watchlist.parse_driver_names("") == ()


def test_row_count():
    """One row per watched name, plus the player if shown, at least one row"""
    assert len(rows("alice smith, bob, carol")) == 4
    assert len(rows("alice smith, bob, carol", show_player=False)) == 3
    assert len(rows("")) == 1
    assert len(rows("", show_player=False)) == 1


def test_exact_match():
    """Exact match ignores case, does not match other names containing it"""
    assert rows("alice smith, BOB") == [(10.0, 2), (2.0, 1), (0.0, PLAYER)]


def test_partial_match():
    """Partial match matches any name containing watched name"""
    assert rows("alice", partial=True) == [(2.0, 1), (0.0, PLAYER)]  # nearest of two matches
    assert rows("alice, carol", partial=True) == [(2.0, 1), (0.0, PLAYER), (-10.0, 3)]


def test_nearer_side():
    """Each watched driver is shown once, on the side with the smaller time gap"""
    assert rows("carol, dave") == [(49.0, 4), (0.0, PLAYER), (-49.0, 5)]


def test_missing_driver():
    """Watched drivers not on track leave empty rows at the bottom"""
    assert rows("alice jones, nobody, bob") == [(10.0, 2), (0.0, PLAYER), (-10.0, 3), NA]
    assert rows("nobody") == [(0.0, PLAYER), NA]


def test_without_player():
    """Player row is left out when show_player is off"""
    assert rows("alice smith, alice jones", show_player=False) == [(2.0, 1), (-10.0, 3)]
    assert rows("nobody", show_player=False) == [NA]


def test_empty_relative_slots(module_info):
    """Unused relative slots (index -1) are never shown"""
    module_info.relative.relativeAhead.append(NA)
    module_info.relative.relativeBehind.insert(0, NA)
    assert rows("bob") == [(10.0, 2), (0.0, PLAYER)]


def test_watched_present():
    """Watchlist hides itself while no watched driver is in the session"""
    rows("nobody")
    assert rows.present is False
    rows("nobody, carol")
    assert rows.present is True
