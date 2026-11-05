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
AMS2 sharedmemory API connector
"""

from __future__ import annotations

import ctypes
import logging
import mmap
import sys
import threading
from time import monotonic

from ..process.timing import LastSectorTime
from .ams2_data import (
    AMS2Constants,
    AMS2SharedMemory,
    GameState,
    PitMode,
    RaceState,
    SessionState,
)

logger = logging.getLogger(__name__)

# Constant
INVALID_INDEX = AMS2Constants.INVALID_INDEX
MAX_PARTICIPANTS = AMS2Constants.STORED_PARTICIPANTS_MAX
MMAP_SIZE = ctypes.sizeof(AMS2SharedMemory)
GAME_STATE_RUNNING = frozenset((
    GameState.INGAME_PLAYING,
    GameState.INGAME_PAUSED,
    GameState.INGAME_INMENU_TIME_TICKING,
))


def platform_mmap(name: str, size: int, prefix: str = "") -> mmap.mmap:
    """Platform memory mapping"""
    if sys.platform == "win32":
        return mmap.mmap(-1, size, f"Local\\{name}")
    with open(f"/dev/shm/{prefix}{name}", "a+b") as file:
        if file.tell() != size:  # file is empty or size doesn't match struct size
            file.seek(0)
            file.truncate(0)
            file.write(b"\0" * size)
            file.flush()
        return mmap.mmap(file.fileno(), size)


class MMapControl:
    """AMS2 memory map control"""

    __slots__ = (
        "_buffer",
        "_mmap_buffer",
        "_realtime",
        "data",
        "update",
    )

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._mmap_buffer = None
        self._realtime: AMS2SharedMemory = None
        self.data = AMS2SharedMemory()
        self.update = self.__buffer_share

    def __del__(self):
        logger.info("sharedmemory: GC: MMap %s", AMS2Constants.MM_FILE_NAME)

    def create(self, access_mode: int = 0, mmap_prefix: str = "") -> None:
        """Create mmap instance & initial accessible copy

        Args:
            access_mode: 0 = copy access, 1 = direct access.
            mmap_prefix: mmap name prefix (Linux only).
        """
        self._mmap_buffer = platform_mmap(AMS2Constants.MM_FILE_NAME, MMAP_SIZE, mmap_prefix)
        if access_mode:
            self.data = AMS2SharedMemory.from_buffer(self._mmap_buffer)
            self.update = self.__buffer_share
        else:
            self._buffer[:] = self._mmap_buffer
            self._realtime = AMS2SharedMemory.from_buffer(self._mmap_buffer)
            self.data = AMS2SharedMemory.from_buffer(self._buffer)
            self.update = self.__buffer_copy
        mode = "Direct" if access_mode else "Copy"
        logger.info("sharedmemory: ACTIVE: %s (%s Access)", AMS2Constants.MM_FILE_NAME, mode)

    def close(self) -> None:
        """Close memory mapping

        Create a final accessible mmap data copy before closing mmap instance.
        """
        self.data = AMS2SharedMemory.from_buffer_copy(self._mmap_buffer)
        self._realtime = None
        try:
            self._mmap_buffer.close()
            logger.info("sharedmemory: CLOSED: %s", AMS2Constants.MM_FILE_NAME)
        except BufferError:
            logger.error("sharedmemory: buffer error while closing %s", AMS2Constants.MM_FILE_NAME)
        self.update = self.__buffer_share

    def __buffer_share(self) -> None:
        """Share buffer access, may result data desync"""

    def __buffer_copy(self) -> None:
        """Copy buffer access, helps avoid data desync

        Sequence number is odd while game is writing data,
        only keep copy if sequence number unchanged during copying.
        """
        realtime = self._realtime
        sequence = realtime.mSequenceNumber
        if sequence & 1 or sequence == self.data.mSequenceNumber:
            return
        buffer = self._mmap_buffer[:]
        if realtime.mSequenceNumber == sequence:
            self._buffer[:] = buffer


class ParticipantTracker:
    """Track per-participant data that is not provided by API

    Attributes:
        grid: starting grid position, 0 = not recorded.
        lap_start: lap start elapsed time (seconds).
        last_valid: last lap valid state.
        pitstops: number of pit stops.
    """

    __slots__ = (
        "_laps",
        "_pit_mode",
        "_invalidated",
        "grid",
        "lap_start",
        "last_valid",
        "pitstops",
    )

    def __init__(self) -> None:
        self._laps = [-1] * MAX_PARTICIPANTS
        self._pit_mode = [PitMode.NONE] * MAX_PARTICIPANTS
        self._invalidated = [False] * MAX_PARTICIPANTS
        self.grid = [0] * MAX_PARTICIPANTS
        self.lap_start = [0.0] * MAX_PARTICIPANTS
        self.last_valid = [True] * MAX_PARTICIPANTS
        self.pitstops = [0] * MAX_PARTICIPANTS

    def reset(self) -> None:
        """Reset data"""
        for index in range(MAX_PARTICIPANTS):
            self._laps[index] = -1
            self._pit_mode[index] = PitMode.NONE
            self._invalidated[index] = False
            self.grid[index] = 0
            self.lap_start[index] = 0.0
            self.last_valid[index] = True
            self.pitstops[index] = 0

    def update(self, data: AMS2SharedMemory, elapsed_time: float) -> None:
        """Update participant data"""
        total = min(max(data.mNumParticipants, 0), MAX_PARTICIPANTS)
        participants = data.mParticipantInfo
        pit_modes = data.mPitModes
        invalidated = data.mLapsInvalidated
        # Record grid position before race starts
        pre_race = data.mSessionState == SessionState.FORMATION_LAP or (
            data.mSessionState == SessionState.RACE
            and data.mRaceState <= RaceState.NOT_STARTED
        )
        for index in range(total):
            if pre_race:
                self.grid[index] = participants[index].mRacePosition
            # Lap start time & last lap valid state
            laps = participants[index].mLapsCompleted
            if self._laps[index] != laps:
                if 0 <= self._laps[index] < laps:
                    self.lap_start[index] = elapsed_time
                    self.last_valid[index] = not self._invalidated[index]
                self._laps[index] = laps
            self._invalidated[index] = invalidated[index]
            # Pit stops
            pit_mode = pit_modes[index]
            if pit_mode == PitMode.IN_PIT and self._pit_mode[index] != PitMode.IN_PIT:
                self.pitstops[index] += 1
            self._pit_mode[index] = pit_mode


class SyncData:
    """Synchronize data with player ID

    Attributes:
        dataset: mmap data set.
        paused: Is API data paused.
        synced: Is player data synced.
        resets: Number of session or player vehicle resets.
        override_player_index: is player index overidden.
        player_index: Local player index.
    """

    __slots__ = (
        "_updating",
        "_update_thread",
        "_event",
        "paused",
        "synced",
        "resets",
        "override_player_index",
        "override_index",
        "player_index",
        "dataset",
        "player_data",
        "elapsed_time",
        "tracker",
    )

    def __init__(self) -> None:
        self._updating = False
        self._update_thread = None
        self._event = threading.Event()

        self.paused = False
        self.synced = False
        self.resets = 0
        self.override_player_index = False
        self.override_index = INVALID_INDEX
        self.player_index = INVALID_INDEX
        self.dataset = MMapControl()
        self.player_data: AMS2SharedMemory = self.dataset.data
        self.elapsed_time = 0.0
        self.tracker = ParticipantTracker()

    def __del__(self):
        logger.info("sharedmemory: GC: SyncData")

    def start(self, access_mode: int, mmap_prefix: str) -> None:
        """Update & sync mmap data copy in separate thread

        Args:
            access_mode: 0 = copy access, 1 = direct access.
        """
        if self._updating:
            logger.warning("sharedmemory: UPDATING: already started")
        else:
            self._updating = True
            # Initialize mmap data
            self.dataset.create(access_mode, mmap_prefix)
            self.player_data = self.dataset.data
            # Setup updating thread
            self._event.clear()
            self._update_thread = threading.Thread(target=self.__update, daemon=True)
            self._update_thread.start()
            logger.info("sharedmemory: UPDATING: thread started")
            logger.info("sharedmemory: player index override: %s", self.override_player_index)

    def stop(self) -> None:
        """Join and stop updating thread, close mmap"""
        if self._updating:
            self._event.set()
            self._updating = False
            self._update_thread.join()
            # Make final copy before close, otherwise mmap won't close if using direct access
            self.dataset.close()
            self.player_data = self.dataset.data
        else:
            logger.warning("sharedmemory: UPDATING: already stopped")

    def __update(self) -> None:
        """Update synced player data"""
        self.paused = True
        self.synced = False
        self.resets = 0

        _event_wait = self._event.wait
        data_freezed = True  # whether data is freezed
        update_delay = 0.5  # longer delay while inactive

        last_session_state = -1
        last_completed_laps = 0
        last_mono_time = monotonic()
        reset_hold_time = 0.0  # hold paused state after reset

        self.elapsed_time = 0.0
        self.tracker.reset()

        while not _event_wait(update_delay):
            self.dataset.update()
            data = self.player_data
            mono_time = monotonic()
            delta_time = min(mono_time - last_mono_time, 0.1)
            last_mono_time = mono_time

            # Data freezes while game not running (menu, replay, exited)
            in_game = (
                data.mVersion > 0
                and data.mGameState in GAME_STATE_RUNNING
                and 0 < data.mNumParticipants <= MAX_PARTICIPANTS
            )
            if data_freezed:
                if in_game:
                    update_delay = 0.01
                    self.paused = data_freezed = False
                    logger.info("sharedmemory: UPDATING: resumed, game state %s", data.mGameState)
                    # Each version only appends fields, so a mismatch is reported but not rejected
                    if data.mVersion != AMS2Constants.SHARED_MEMORY_VERSION:
                        logger.warning(
                            "sharedmemory: version %s, expected %s, data added in other versions may be invalid",
                            data.mVersion,
                            AMS2Constants.SHARED_MEMORY_VERSION,
                        )
                else:
                    continue
            elif not in_game:
                update_delay = 0.5
                self.paused = data_freezed = True
                self.synced = False
                logger.info("sharedmemory: UPDATING: paused, game state %s", data.mGameState)
                continue

            # Get player index
            if self.override_player_index:
                player_index = self.override_index
            else:
                player_index = data.mViewedParticipantIndex
            if 0 <= player_index < data.mNumParticipants:
                self.player_index = player_index
                self.synced = True
            else:
                self.synced = False

            # Check session or vehicle resets
            completed_laps = data.mParticipantInfo[max(self.player_index, 0)].mLapsCompleted
            if (
                last_session_state != data.mSessionState  # session changed
                or data.mGameState == GameState.INGAME_RESTARTING  # session restarted
                or last_completed_laps > completed_laps  # lap count reset
            ):
                self.elapsed_time = 0.0
                self.resets += 1
                self.tracker.reset()
                # Signal paused state briefly, so that modules reset previous session data,
                # as AMS2 may switch session without leaving game state
                reset_hold_time = mono_time + 1.5
                self.paused = True
                logger.info("sharedmemory: UPDATING: session reset, session state %s", data.mSessionState)
            elif reset_hold_time and mono_time >= reset_hold_time:
                reset_hold_time = 0.0
                self.paused = False
            last_session_state = data.mSessionState
            last_completed_laps = completed_laps

            # Session elapsed time, only ticking while game not paused
            if data.mGameState != GameState.INGAME_PAUSED:
                self.elapsed_time += delta_time

            self.tracker.update(data, self.elapsed_time)

        logger.info("sharedmemory: UPDATING: thread stopped")


class AMS2Info:
    """AMS2 shared memory data output"""

    __slots__ = (
        "_sync",
        "_access_mode",
        "_mmap_prefix",
        "_state_override",
        "_active_state",
        "_last_damage",
        "_last_collision",
        "_last_impact_time",
        "_last_sector_time",
    )

    def __init__(self) -> None:
        self._sync = SyncData()
        self._access_mode = 0
        self._mmap_prefix = ""
        self._state_override = False
        self._active_state = False
        self._last_damage = 0.0
        self._last_collision = (INVALID_INDEX, 0.0)
        self._last_impact_time = 0.0
        self._last_sector_time = LastSectorTime()

    def __del__(self):
        logger.info("sharedmemory: GC: AMS2Info")

    def start(self) -> None:
        """Start data updating thread"""
        self._sync.start(self._access_mode, self._mmap_prefix)

    def stop(self) -> None:
        """Stop data updating thread"""
        self._sync.stop()

    def setPrefix(self, prefix: str = "") -> None:
        """Set AMS2 mmap file name prefix, can only be customized on Linux"""
        if sys.platform == "win32":
            self._mmap_prefix = "Local\\"  # for displaying console logging only
        else:
            self._mmap_prefix = prefix

    def setMode(self, mode: int = 0) -> None:
        """Set mmap access mode

        Args:
            mode: 0 = copy access, 1 = direct access
        """
        self._access_mode = mode

    def setStateOverride(self, state: bool = False) -> None:
        """Enable state override"""
        self._state_override = state

    def setActiveState(self, state: bool = False) -> None:
        """Set state override"""
        self._active_state = state

    def setPlayerOverride(self, state: bool = False) -> None:
        """Enable player index override state"""
        self._sync.override_player_index = state

    def setPlayerIndex(self, index: int = INVALID_INDEX) -> None:
        """Manual override player index"""
        self._sync.override_index = min(max(index, INVALID_INDEX), MAX_PARTICIPANTS - 1)

    @property
    def ams2LastSectorTime(self) -> LastSectorTime:
        """AMS2 player last sector time"""
        data = self._sync.player_data
        sector_index = data.mParticipantInfo[self.playerIndex].mCurrentSector
        if sector_index == 1:
            accumulated = data.mCurrentSector1Time
        elif sector_index == 2:
            accumulated = data.mCurrentSector1Time + data.mCurrentSector2Time
        else:
            accumulated = data.mLastLapTime
        return self._last_sector_time.update(
            sector_index,
            accumulated,
            data.mLastLapTime,
            not data.mLapInvalidated,
        )

    @property
    def ams2LastImpactTime(self) -> float:
        """AMS2 player last impact time stamp, estimated from damage changes & opponent collisions"""
        data = self._sync.player_data
        damage = data.mAeroDamage + data.mEngineDamage + sum(data.mSuspensionDamage)
        if self._last_damage != damage:
            if self._last_damage < damage:
                self._last_impact_time = self._sync.elapsed_time
            self._last_damage = damage
        # Opponent collision is reported even with damage disabled
        collision = data.mLastOpponentCollisionIndex, data.mLastOpponentCollisionMagnitude
        if self._last_collision != collision:
            if collision[0] >= 0 and collision[1] > 0:
                self._last_impact_time = self._sync.elapsed_time
            self._last_collision = collision
        if self._last_impact_time > self._sync.elapsed_time:  # session reset
            self._last_impact_time = 0.0
        return self._last_impact_time

    @property
    def ams2Data(self) -> AMS2SharedMemory:
        """AMS2 shared memory data"""
        return self._sync.player_data

    @property
    def ams2Tracker(self) -> ParticipantTracker:
        """AMS2 participant tracker data"""
        return self._sync.tracker

    @property
    def playerIndex(self) -> int:
        """Local player's index"""
        return max(self._sync.player_index, 0)

    @property
    def isPaused(self) -> bool:
        """Check whether data stopped updating"""
        return self._sync.paused

    @property
    def isActive(self) -> bool:
        """Check whether in active (driving or overriding) state"""
        if self._state_override:
            return self._active_state
        data = self._sync.player_data
        return (
            self._sync.synced
            and not self._sync.paused
            and data.mGameState != GameState.INGAME_PAUSED
            and data.mMaxRPM > 0
        )

    @property
    def vehicleResets(self) -> int:
        """Number of session or player vehicle resets"""
        return self._sync.resets

    @property
    def elapsed(self) -> float:
        """Current session elapsed time"""
        return self._sync.elapsed_time
