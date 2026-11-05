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
AMS2 API connector
"""

from ..constant import API
from ..validator import bytes_decoder
from . import ams2_reader, ams2_sharedmemory
from ._connector import APIDataReader, Connector


class SimAMS2(Connector):
    """Automobilista 2 - AMS2 Native Sharedmemory API"""

    NAME = API.NAME_AMS2
    LEGACY = False
    __slots__ = (
        "_shmmapi",
    )

    def __init__(self):
        self._shmmapi = ams2_sharedmemory.AMS2Info()

    def start(self):
        self._shmmapi.start()

    def stop(self):
        self._shmmapi.stop()

    def reader(self) -> APIDataReader:
        shmm = self._shmmapi
        return APIDataReader(
            ams2_reader.State(shmm),
            ams2_reader.Brake(shmm),
            ams2_reader.ElectricMotor(shmm),
            ams2_reader.Engine(shmm),
            ams2_reader.Inputs(shmm),
            ams2_reader.Lap(shmm),
            ams2_reader.Session(shmm),
            ams2_reader.Switch(shmm),
            ams2_reader.Timing(shmm),
            ams2_reader.Tyre(shmm),
            ams2_reader.Vehicle(shmm),
            ams2_reader.Wheel(shmm),
        )

    def setup(self, config: dict):
        self._shmmapi.setPrefix(config["memory_map_prefix"])
        self._shmmapi.setMode(config["access_mode"])
        self._shmmapi.setStateOverride(config["enable_active_state_override"])
        self._shmmapi.setActiveState(config["active_state"])
        self._shmmapi.setPlayerOverride(config["enable_player_index_override"])
        self._shmmapi.setPlayerIndex(config["player_index"])
        ams2_reader.tostr = bytes_decoder(config["character_encoding"])
