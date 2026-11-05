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

Relative widget that only shows the drivers named in "watched_driver_names" (and the player).
"""

from __future__ import annotations

from .. import minfo
from . import relative


def parse_driver_names(text: str) -> tuple[str, ...]:
    """Parse comma separated driver names into lowercase name list"""
    return tuple(name.strip().lower() for name in text.split(",") if name.strip())


class Realtime(relative.Realtime):
    """Draw widget"""

    def __init__(self, config, widget_name):
        super().__init__(config, widget_name)
        self.watched_names = parse_driver_names(self.wcfg["watched_driver_names"])
        self.partial_match = self.wcfg["enable_partial_name_match"]
        self.match_cache: dict[str, bool] = {}

    def relative_list(self, player_idx: int):
        """Relative rows of watched drivers only

        Every opponent is in both relative lists (time gap ahead and behind on track),
        keep each watched driver on the side with the smaller gap, as Relative does.
        """
        dataset = minfo.vehicles.dataSet
        gap_behind = {
            index: -time_gap
            for time_gap, index in minfo.relative.relativeBehind
            if index >= 0 and self.is_watched(dataset[index].driverName)
        }
        watched_ahead = []
        watched_behind = []
        for time_gap, index in minfo.relative.relativeAhead:
            if index not in gap_behind:
                continue
            if time_gap <= gap_behind[index]:
                watched_ahead.append((time_gap, index))
            else:
                watched_behind.append((-gap_behind[index], index))
        # Same order as relative lists: ahead furthest first, behind nearest first
        watched_ahead.sort(reverse=True)
        watched_behind.sort(reverse=True)
        return relative.relative_data(
            watched_ahead,
            watched_behind,
            player_idx,
            self.max_veh_front,
            self.max_veh_behind,
        )

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
