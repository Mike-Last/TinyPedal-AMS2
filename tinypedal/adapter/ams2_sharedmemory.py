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
from math import hypot
from time import monotonic

from ..calculation import rotate_coordinate
from ..process.timing import LastSectorTime
from ..validator import infnan_to_zero as rmnan
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
# Game states where the session has ended (main menu, menu replay, game closed)
GAME_STATE_LEFT_SESSION = frozenset((
    GameState.EXITED,
    GameState.FRONT_END,
    GameState.FRONT_END_REPLAY,
))
# Body parts of damage severity, direction in vehicle frame (+x right, +y behind)
_DIAGONAL = 0.7071067811865476
BODY_PART_DIRECTIONS = (
    (-_DIAGONAL, -_DIAGONAL), (0.0, -1.0), (_DIAGONAL, -_DIAGONAL),  # front left, front, front right
    (-1.0, 0.0), (1.0, 0.0),  # left, right
    (-_DIAGONAL, _DIAGONAL), (0.0, 1.0), (_DIAGONAL, _DIAGONAL),  # rear left, rear, rear right
)
BODY_PARTS = len(BODY_PART_DIRECTIONS)
MAX_PART_SEVERITY = 2.0  # heavy damage, above is detached
IMPACT_WINDOW = 0.3  # seconds a velocity change or collision stays linked to a damage rise
MIN_IMPACT_DELTA_SPEED = 0.5  # m/s velocity change between samples, ignores most normal driving


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

    Data is stored by participant index, and follows the driver name,
    so that it stays with the driver if participant indexes change
    (drivers joining or leaving), and does not pass on to another driver.

    Attributes:
        grid: starting grid position, 0 = not recorded.
        lap_start: lap start elapsed time (seconds).
        last_valid: last lap valid state.
        pitstops: number of pit stops.
    """

    __slots__ = (
        "_names",
        "_total",
        "_departed",
        "_laps",
        "_pit_mode",
        "_invalidated",
        "grid",
        "lap_start",
        "last_valid",
        "pitstops",
    )

    def __init__(self) -> None:
        self._names = [b""] * MAX_PARTICIPANTS
        self._total = 0
        self._departed: dict[bytes, tuple] = {}
        self._laps = [-1] * MAX_PARTICIPANTS
        self._pit_mode = [PitMode.NONE] * MAX_PARTICIPANTS
        self._invalidated = [False] * MAX_PARTICIPANTS
        self.grid = [0] * MAX_PARTICIPANTS
        self.lap_start = [0.0] * MAX_PARTICIPANTS
        self.last_valid = [True] * MAX_PARTICIPANTS
        self.pitstops = [0] * MAX_PARTICIPANTS

    def reset(self) -> None:
        """Reset data"""
        self._total = 0
        self._departed.clear()
        for index in range(MAX_PARTICIPANTS):
            self._names[index] = b""
            self._reset_index(index)

    def _reset_index(self, index: int) -> None:
        """Reset data of participant index"""
        self._laps[index] = -1
        self._pit_mode[index] = PitMode.NONE
        self._invalidated[index] = False
        self.grid[index] = 0
        self.lap_start[index] = 0.0
        self.last_valid[index] = True
        self.pitstops[index] = 0

    def _save_index(self, index: int) -> None:
        """Save data of participant index under driver name, before index changes driver"""
        name = self._names[index]
        if name:
            self._departed[name] = (
                self._laps[index],
                self._pit_mode[index],
                self._invalidated[index],
                self.grid[index],
                self.lap_start[index],
                self.last_valid[index],
                self.pitstops[index],
            )
        self._names[index] = b""

    def _load_index(self, index: int, name: bytes) -> None:
        """Load saved data of driver name into participant index, or reset if new driver"""
        self._names[index] = name
        saved = self._departed.pop(name, None) if name else None
        if saved is None:
            self._reset_index(index)
            return
        (
            self._laps[index],
            self._pit_mode[index],
            self._invalidated[index],
            self.grid[index],
            self.lap_start[index],
            self.last_valid[index],
            self.pitstops[index],
        ) = saved

    def _sync_names(self, participants, total: int) -> None:
        """Move data with driver names if participant indexes changed"""
        changed = [
            index for index in range(total)
            if self._names[index] != participants[index].mName
        ]
        if not changed and total >= self._total:
            self._total = total
            return
        # Save all changed (and no longer used) indexes first, then load,
        # so that drivers swapping indexes keep their data
        for index in changed:
            self._save_index(index)
        for index in range(total, self._total):
            self._save_index(index)
            self._reset_index(index)
        for index in changed:
            self._load_index(index, participants[index].mName)
        self._total = total

    def update(self, data: AMS2SharedMemory, elapsed_time: float) -> None:
        """Update participant data"""
        total = min(max(data.mNumParticipants, 0), MAX_PARTICIPANTS)
        participants = data.mParticipantInfo
        pit_modes = data.mPitModes
        invalidated = data.mLapsInvalidated
        self._sync_names(participants, total)
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


class DamageTracker:
    """Track impact time, impact direction and damage location of player vehicle

    AMS2 only reports total aero damage, with no impact or location data, so:
        - An impact is a rise in damage, or a new opponent collision
          (reported even with damage disabled).
        - Impact direction comes from the opponent's position for a collision,
          otherwise from the largest sudden change in velocity shortly before the impact,
          as the car is pushed away from where it was hit.
        - Each rise in aero damage is spread over the body parts that face the impact,
          so the total of all parts stays at aero damage x 16 (8 parts, max severity 2).

    Directions use the vehicle frame of the radar widget: +x right, +y behind.

    Attributes:
        timestamp: last impact elapsed time (seconds).
        position: last impact direction x, y (unit length), (0, 0) = unknown.
        severity: body part damage severity, 0 = none, 1 = light, 2 = heavy,
            order: front left, front, front right, left, right, rear left, rear, rear right.
    """

    __slots__ = (
        "_player_index",
        "_aero",
        "_damage",
        "_velocity",
        "_collision",
        "_direction",
        "_direction_time",
        "_direction_strength",
        "timestamp",
        "position",
        "severity",
    )

    def __init__(self) -> None:
        self._player_index = INVALID_INDEX
        self._aero = 0.0
        self._damage = 0.0
        self._velocity = (0.0, 0.0)
        self._collision = (INVALID_INDEX, 0.0)
        self._direction = (0.0, 0.0)
        self._direction_time = 0.0
        self._direction_strength = 0.0
        self.timestamp = 0.0
        self.position = (0.0, 0.0)
        self.severity = (0.0,) * BODY_PARTS

    def reset(self) -> None:
        """Reset on session or vehicle change, next update starts from current damage"""
        self._player_index = INVALID_INDEX
        self.timestamp = 0.0
        self.position = (0.0, 0.0)

    def update(self, data: AMS2SharedMemory, player_index: int, elapsed_time: float) -> None:
        """Update impact & damage of player vehicle"""
        if not 0 <= player_index < MAX_PARTICIPANTS:
            return
        aero = min(max(rmnan(data.mAeroDamage), 0.0), 1.0)
        damage = aero + rmnan(data.mEngineDamage) + sum(map(rmnan, data.mSuspensionDamage))
        velocity = rmnan(data.mWorldVelocity[0]), -rmnan(data.mWorldVelocity[2])
        collision = data.mLastOpponentCollisionIndex, data.mLastOpponentCollisionMagnitude

        # First update, or viewing another vehicle, start from its current damage
        if self._player_index != player_index:
            self._player_index = player_index
            self._aero = aero
            self._damage = damage
            self._velocity = velocity
            self._collision = collision
            self._direction_strength = 0.0
            self.severity = (aero * MAX_PART_SEVERITY,) * BODY_PARTS
            return

        yaw = -rmnan(data.mOrientations[player_index][1])  # same as reader orientation_yaw
        if elapsed_time - self._direction_time > IMPACT_WINDOW:
            self._direction_strength = 0.0

        # Sudden velocity change, the car is pushed away from the impact
        delta_x = velocity[0] - self._velocity[0]
        delta_y = velocity[1] - self._velocity[1]
        self._velocity = velocity
        strength = hypot(delta_x, delta_y)
        if strength >= MIN_IMPACT_DELTA_SPEED and strength > self._direction_strength:
            self._set_direction(yaw, -delta_x, -delta_y, strength, elapsed_time)

        # Opponent collision, direction of the opponent
        if self._collision != collision:
            self._collision = collision
            opponent_index, magnitude = collision
            if 0 <= opponent_index < MAX_PARTICIPANTS and opponent_index != player_index and magnitude > 0:
                player_pos = data.mParticipantInfo[player_index].mWorldPosition
                opponent_pos = data.mParticipantInfo[opponent_index].mWorldPosition
                self._set_direction(
                    yaw,
                    opponent_pos[0] - player_pos[0],
                    player_pos[2] - opponent_pos[2],
                    float("inf"),  # takes priority over velocity change
                    elapsed_time,
                )
                self.timestamp = elapsed_time
                self.position = self._direction

        has_direction = self._direction_strength > 0
        # Damage rise
        if self._damage != damage:
            if self._damage < damage:
                self.timestamp = elapsed_time
                if has_direction:
                    self.position = self._direction
            self._damage = damage

        # Aero damage rise spreads over body parts facing the impact, drop (repair) scales all parts
        if self._aero < aero:
            self.severity = spread_damage(
                self.severity,
                (aero - self._aero) * MAX_PART_SEVERITY * BODY_PARTS,
                self._direction if has_direction else None,
            )
        elif self._aero > aero:
            scale = aero / self._aero
            self.severity = tuple(part * scale for part in self.severity)
        self._aero = aero

    def _set_direction(self, yaw: float, pos_x: float, pos_y: float, strength: float, elapsed_time: float) -> None:
        """Set impact direction from world x, y offset, rotated to vehicle frame"""
        dir_x, dir_y = rotate_coordinate(yaw - 3.14159265, pos_x, pos_y)
        length = hypot(dir_x, dir_y)
        if length > 0:
            self._direction = dir_x / length, dir_y / length
            self._direction_time = elapsed_time
            self._direction_strength = strength


def spread_damage(
    severity: tuple[float, ...], amount: float, direction: tuple[float, float] | None
) -> tuple[float, ...]:
    """Spread damage amount over body parts facing the impact direction

    Parts are weighted by how directly they face the impact, a part only takes damage
    up to max severity, and any excess goes to the remaining parts.
    Spread evenly if direction unknown.
    """
    if direction is None:
        weights = [1.0] * BODY_PARTS
    else:
        # Ignore parts at (or rounding error from) right angles, which would show as light damage
        weights = [
            facing * facing if (facing := direction[0] * part_x + direction[1] * part_y) > 1e-6 else 0.0
            for part_x, part_y in BODY_PART_DIRECTIONS
        ]
    parts = list(severity)
    while amount > 1e-9:
        open_parts = [index for index in range(BODY_PARTS) if parts[index] < MAX_PART_SEVERITY]
        if not open_parts:
            break
        total_weight = sum(weights[index] for index in open_parts)
        if total_weight <= 0:  # parts facing impact are full, spread to the rest
            weights = [1.0] * BODY_PARTS
            continue
        excess = 0.0
        for index in open_parts:
            value = parts[index] + amount * weights[index] / total_weight
            if value > MAX_PART_SEVERITY:
                excess += value - MAX_PART_SEVERITY
                value = MAX_PART_SEVERITY
            parts[index] = value
        amount = excess
    return tuple(parts)


class SessionCheck:
    """Check session or player vehicle resets

    AMS2 has no reset counter, a reset is detected from session state changes,
    session restarts, player completed laps going back, and returning from the main menu.
    """

    __slots__ = (
        "_session_state",
        "_player_index",
        "_completed_laps",
        "_left_session",
    )

    def __init__(self) -> None:
        self._session_state = -1
        self._player_index = INVALID_INDEX
        self._completed_laps = 0
        self._left_session = False

    def check_game_state(self, game_state: int) -> None:
        """Check game state on every sample, including while data is paused

        Data is not read while the game is in menus, so session changes there are not seen.
        Leaving to the main menu ends the session, the next session is a reset,
        even with the same session type and lap count. Replays during a session do not count.
        """
        if game_state in GAME_STATE_LEFT_SESSION:
            self._left_session = True

    def is_reset(self, data: AMS2SharedMemory, player_index: int) -> bool:
        """Is session or player vehicle reset since last check

        Completed laps are only compared for the same player index,
        so that viewing another vehicle (with fewer laps) is not a reset.
        """
        completed_laps = data.mParticipantInfo[max(player_index, 0)].mLapsCompleted
        is_reset = (
            self._left_session  # returned from main menu
            or self._session_state != data.mSessionState  # session changed
            or data.mGameState == GameState.INGAME_RESTARTING  # session restarted
            or (  # lap count reset
                self._player_index == player_index
                and self._completed_laps > completed_laps
            )
        )
        self._session_state = data.mSessionState
        self._player_index = player_index
        self._completed_laps = completed_laps
        self._left_session = False
        return is_reset


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
        "damage",
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
        self.damage = DamageTracker()

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

        session_check = SessionCheck()
        last_mono_time = monotonic()
        reset_hold_time = 0.0  # hold paused state after reset

        self.elapsed_time = 0.0
        self.tracker.reset()
        self.damage.reset()

        while not _event_wait(update_delay):
            self.dataset.update()
            data = self.player_data
            session_check.check_game_state(data.mGameState)
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
            if session_check.is_reset(data, self.player_index):
                self.elapsed_time = 0.0
                self.resets += 1
                self.tracker.reset()
                self.damage.reset()
                # Signal paused state briefly, so that modules reset previous session data,
                # as AMS2 may switch session without leaving game state
                reset_hold_time = mono_time + 1.5
                self.paused = True
                logger.info("sharedmemory: UPDATING: session reset, session state %s", data.mSessionState)
            elif reset_hold_time and mono_time >= reset_hold_time:
                reset_hold_time = 0.0
                self.paused = False

            # Session elapsed time, only ticking while game not paused
            if data.mGameState != GameState.INGAME_PAUSED:
                self.elapsed_time += delta_time

            self.tracker.update(data, self.elapsed_time)
            if self.synced:
                self.damage.update(data, self.player_index, self.elapsed_time)

        logger.info("sharedmemory: UPDATING: thread stopped")


class AMS2Info:
    """AMS2 shared memory data output"""

    __slots__ = (
        "_sync",
        "_access_mode",
        "_mmap_prefix",
        "_state_override",
        "_active_state",
        "_last_sector_time",
    )

    def __init__(self) -> None:
        self._sync = SyncData()
        self._access_mode = 0
        self._mmap_prefix = ""
        self._state_override = False
        self._active_state = False
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
    def ams2Damage(self) -> DamageTracker:
        """AMS2 player impact & damage location data"""
        return self._sync.damage

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
