#  TinyPedal is an open-source overlay application for racing simulation.
#  Copyright (C) 2022-2026 TinyPedal developers, see contributors.md file
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
Friends Widget
"""

from __future__ import annotations

from .. import calculation as calc
from .. import minfo
from ..constant import DATA
from ..formatter import shorten_driver_name
from ._base import Overlay


def as_rows(bars) -> tuple:
    """Make sure bars is a tuple, as set_rawtext returns single bar if count is 1"""
    return bars if isinstance(bars, tuple) else (bars,)


def parse_friend_names(text: str) -> tuple[str, ...]:
    """Parse comma separated friend names into lowercase name list"""
    return tuple(name.strip().lower() for name in text.split(",") if name.strip())


class Realtime(Overlay):
    """Draw widget"""

    def __init__(self, config, widget_name):
        # Assign base setting
        super().__init__(config, widget_name)
        layout = self.set_grid_layout(gap_vert=self.wcfg["bar_gap"])
        self.set_primary_layout(layout=layout)

        # Config font
        font = self.config_font(
            self.wcfg["font_name"],
            self.wcfg["font_size"],
            self.wcfg["font_weight"],
        )
        self.setFont(font)
        font_m = self.get_font_metrics(font)

        # Config variable
        bar_padx = self.set_padding(self.wcfg["font_size"], self.wcfg["bar_padding"])
        row_start = 1 if self.wcfg["show_caption"] else 0
        self.drv_width = max(int(self.wcfg["driver_name_width"]), 1)
        self.friend_names = parse_friend_names(self.wcfg["friend_names"])
        self.partial_match = self.wcfg["enable_partial_name_match"]
        self.show_player = self.wcfg["show_player"]
        self.show_placeholder = self.wcfg["show_placeholder_when_empty"] and self.wcfg["show_driver_name"]
        self.placeholder_shown = False

        # Max display rows
        self.veh_range = max(int(self.wcfg["number_of_friends"]), 1) + self.show_player

        # Empty dataset
        self.row_visible = [True] * self.veh_range
        self.match_cache: dict[str, bool] = {}

        # Driver position
        if self.wcfg["show_position"]:
            self.bars_pos = as_rows(self.set_rawtext(
                padding=bar_padx,
                width=2 * font_m.width,
                fixed_height=font_m.height,
                offset_y=font_m.voffset,
                fg_color=self.wcfg["font_color_position"],
                bg_color=self.wcfg["background_color_position"],
                count=self.veh_range,
            ))
            self.set_grid_layout_table_column(
                layout=layout,
                targets=self.bars_pos,
                row_start=row_start,
                column=self.wcfg["display_order_position"],
            )
        # Driver name
        if self.wcfg["show_driver_name"]:
            self.bar_style_drv = (
                (
                    self.wcfg["font_color_driver_name"],
                    self.wcfg["background_color_driver_name"],
                ),
                (
                    self.wcfg["font_color_player_driver_name"],
                    self.wcfg["background_color_player_driver_name"],
                ),
            )
            self.bars_drv = as_rows(self.set_rawtext(
                padding=bar_padx,
                width=self.drv_width * font_m.width,
                fixed_height=font_m.height,
                offset_y=font_m.voffset,
                fg_color=self.bar_style_drv[0][0],
                bg_color=self.bar_style_drv[0][1],
                alignment=self.wcfg["driver_name_text_alignment"],
                count=self.veh_range,
            ))
            self.set_grid_layout_table_column(
                layout=layout,
                targets=self.bars_drv,
                row_start=row_start,
                column=self.wcfg["display_order_driver_name"],
            )
        # Last laptime
        if self.wcfg["show_laptime"]:
            self.bars_lpt = as_rows(self.set_rawtext(
                padding=bar_padx,
                width=8 * font_m.width,
                fixed_height=font_m.height,
                offset_y=font_m.voffset,
                fg_color=self.wcfg["font_color_laptime"],
                bg_color=self.wcfg["background_color_laptime"],
                count=self.veh_range,
            ))
            self.set_grid_layout_table_column(
                layout=layout,
                targets=self.bars_lpt,
                row_start=row_start,
                column=self.wcfg["display_order_laptime"],
            )
        # Best laptime
        if self.wcfg["show_best_laptime"]:
            self.bars_blp = as_rows(self.set_rawtext(
                padding=bar_padx,
                width=8 * font_m.width,
                fixed_height=font_m.height,
                offset_y=font_m.voffset,
                fg_color=self.wcfg["font_color_best_laptime"],
                bg_color=self.wcfg["background_color_best_laptime"],
                count=self.veh_range,
            ))
            self.set_grid_layout_table_column(
                layout=layout,
                targets=self.bars_blp,
                row_start=row_start,
                column=self.wcfg["display_order_best_laptime"],
            )

        # Caption
        if self.wcfg["show_caption"]:
            self.set_grid_layout_table_caption(
                layout=layout,
                padding=bar_padx,
            )

        # Hide all rows until friends found
        for idx in range(self.veh_range):
            self.update_row(idx, None, False)
            self.row_visible[idx] = False
        self.set_placeholder(True)

    def timerEvent(self, event):
        """Update when vehicle on track"""
        friends_list = self.find_friends()

        for idx in range(self.veh_range):
            if idx < len(friends_list):
                self.row_visible[idx] = True
                self.update_row(idx, minfo.vehicles.dataSet[friends_list[idx]], True)
            elif self.row_visible[idx]:
                self.row_visible[idx] = False
                self.update_row(idx, None, False)

        self.set_placeholder(not friends_list)

    def set_placeholder(self, empty: bool):
        """Show placeholder text in first row while no friends found

        Keeps widget window visible, so that it can be captured by other apps (such as OpenKneeboard).
        """
        if not self.show_placeholder or self.placeholder_shown == empty:
            return
        self.placeholder_shown = empty
        if empty:
            target = self.bars_drv[0]
            target.last = None  # force redraw once friend found
            target.text = f"{self.wcfg['placeholder_text']:.{self.drv_width}}"
            target.fg = self.wcfg["font_color_placeholder"]
            target.bg = self.wcfg["background_color_placeholder"]
            self.toggle_visibility(target, True)

    def find_friends(self) -> list[int]:
        """Find vehicle index of friends (and player), sort by overall position"""
        if not self.friend_names and not self.show_player:
            return []
        found = []
        dataset = minfo.vehicles.dataSet
        for index in range(min(minfo.vehicles.totalVehicles, len(dataset))):
            veh_info = dataset[index]
            if veh_info.isPlayer:
                if self.show_player:
                    found.append((veh_info.positionOverall, index))
            elif self.is_friend(veh_info.driverName):
                found.append((veh_info.positionOverall, index))
        found.sort()
        return [index for _, index in found[:self.veh_range]]

    def is_friend(self, driver_name: str) -> bool:
        """Is driver name matching friend names (case insensitive)"""
        matched = self.match_cache.get(driver_name)
        if matched is None:
            name = driver_name.lower()
            if not name:
                matched = False
            elif self.partial_match:
                matched = any(friend in name for friend in self.friend_names)
            else:
                matched = name in self.friend_names
            self.match_cache[driver_name] = matched
        return matched

    def update_row(self, idx: int, veh_info, state: bool):
        """Update row"""
        if veh_info is None:
            position = 0
            driver_name = ""
            is_player = False
            laptime_last = ""
            laptime_best = ""
        else:
            position = veh_info.positionOverall
            driver_name = veh_info.driverName
            is_player = veh_info.isPlayer
            laptime_last = self.set_laptime(veh_info.lastLapTime, veh_info.isValidLap)
            laptime_best = self.set_laptime(veh_info.bestLapTime)
        if self.wcfg["show_position"]:
            self.update_pos(self.bars_pos[idx], position, state)
        if self.wcfg["show_driver_name"]:
            self.update_drv(self.bars_drv[idx], driver_name, is_player, state)
        if self.wcfg["show_laptime"]:
            self.update_lpt(self.bars_lpt[idx], laptime_last, state)
        if self.wcfg["show_best_laptime"]:
            self.update_lpt(self.bars_blp[idx], laptime_best, state)

    # GUI update methods
    def update_pos(self, target, *data):
        """Driver position"""
        if target.last != data:
            target.last = data
            target.text = f"{data[0]:02d}" if data[0] > 0 else "--"
            self.toggle_visibility(target, data[-1])

    def update_drv(self, target, *data):
        """Driver name"""
        if target.last != data:
            target.last = data
            if self.wcfg["driver_name_shorten"]:
                text = shorten_driver_name(data[0])
            else:
                text = data[0]
            if self.wcfg["driver_name_uppercase"]:
                text = text.upper()
            target.text = f"{text:.{self.drv_width}}"
            target.fg, target.bg = self.bar_style_drv[data[1]]
            self.toggle_visibility(target, data[-1])

    def update_lpt(self, target, *data):
        """Vehicle laptime"""
        if target.last != data:
            target.last = data
            target.text = data[0][:8]
            self.toggle_visibility(target, data[-1])

    # Additional methods
    def toggle_visibility(self, target, state):
        """Hide bar if unavailable"""
        target.update()
        if target.state == state:
            return
        target.state = state
        target.setHidden(not state)

    @staticmethod
    def set_laptime(laptime: float, valid: bool = True) -> str:
        """Set lap time"""
        if 0 < laptime < DATA.MAX_SECONDS:
            if valid:
                return calc.sec2laptime_full(laptime)
            return f"*{calc.sec2laptime_full(laptime)}"
        return DATA.TEXT_NOLAPTIME
