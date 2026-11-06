#  TinyPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
#  Copyright (C) 2026 Mike Last - unofficial AMS2 fork additions, written with AI assistance
#
#  This file is part of TinyPedal.
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
Watchlist Widget

Relative widget that only shows the drivers named in "watched_driver_names" (and the player),
with one row per watched name (plus the player).
"""

from __future__ import annotations

from .. import minfo
from ..constant import DATA
from . import relative


def parse_driver_names(text: str) -> tuple[str, ...]:
    """Parse comma separated driver names into lowercase name list"""
    return tuple(name.strip().lower() for name in text.split(",") if name.strip())


class Realtime(relative.Realtime):
    """Draw widget"""

    def __init__(self, config, widget_name):
        self.watched_names: tuple[str, ...] = ()
        self.show_player = True
        super().__init__(config, widget_name)
        self.partial_match = self.wcfg["enable_partial_name_match"]
        self.auto_hide = self.wcfg["enable_auto_hide_without_watched_driver"]
        self.match_cache: dict[str, bool] = {}
        self.watched_present = False

    def timerEvent(self, event):
        """Update rows, hide while no watched driver is in the session"""
        super().timerEvent(event)
        if self.auto_hide:
            self.set_widget_hidden(not self.watched_present)

    def row_count(self, rows: int) -> int:
        """One row per watched driver name, plus the player"""
        self.watched_names = parse_driver_names(self.wcfg["watched_driver_names"])
        self.show_player = bool(self.wcfg["show_player"])
        return max(len(self.watched_names) + self.show_player, 1)

    def relative_list(self, player_idx: int):
        """Relative rows of watched drivers only, in track order, empty rows last

        Every opponent is in both relative lists (time gap ahead and behind on track),
        keep each watched driver on the side with the smaller gap, as Relative does.
        """
        dataset = minfo.vehicles.dataSet
        gap_behind = {
            index: -time_gap
            for time_gap, index in minfo.relative.relativeBehind
            if index >= 0 and self.is_watched(dataset[index].driverName)
        }
        self.watched_present = bool(gap_behind)
        watched = [
            (time_gap, index) if time_gap <= gap_behind[index] else (-gap_behind[index], index)
            for time_gap, index in minfo.relative.relativeAhead
            if index in gap_behind
        ]
        # Keep the nearest drivers when more match than rows (partial match)
        max_watched = self.veh_range - self.show_player
        if len(watched) > max_watched:
            watched.sort(key=lambda data: abs(data[0]))
            del watched[max_watched:]
        if self.show_player:
            watched.append((0.0, player_idx))
        # Same order as relative: ahead furthest first, player, behind nearest first
        watched.sort(reverse=True)
        watched.extend([DATA.RELATIVE_NA] * (self.veh_range - len(watched)))
        return watched

    def is_watched(self, driver_name: str) -> bool:
        """Is driver name matching watched driver names (case insensitive)"""
        matched = self.match_cache.get(driver_name)
        if matched is None:
            name = driver_name.lower()
            if not name:
                matched = False
            elif self.partial_match:
                matched = any(watched in name for watched in self.watched_names)
            else:
                matched = name in self.watched_names
            self.match_cache[driver_name] = matched
        return matched
