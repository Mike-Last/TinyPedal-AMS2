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
AMS2 API data reader
"""

from __future__ import annotations

from ..calculation import atan2, lap_progress_distance, min_nonzero
from ..constant import DATA
from ..formatter import strip_invalid_char
from ..validator import bytes_decoder
from ..validator import infnan_to_zero as rmnan
from . import _reader
from .ams2_data import (
    TERRAIN_OFFROAD,
    CarFlags,
    DrsState,
    FlagColour,
    PitMode,
    PitSchedule,
    RaceState,
    SessionState,
    TyreFlags,
    YellowFlagState,
)
from .ams2_sharedmemory import MAX_PARTICIPANTS, AMS2Info

tostr = bytes_decoder()

TAU = 6.283185307179586
KELVIN_TO_CELSIUS = -273.15
PIT_REQUESTED = frozenset((
    PitSchedule.PLAYER_REQUESTED,
    PitSchedule.ENGINEER_REQUESTED,
    PitSchedule.DAMAGE_REQUESTED,
    PitSchedule.MANDATORY,
))
PIT_PENALTY = frozenset((
    PitSchedule.DRIVE_THROUGH,
    PitSchedule.STOP_GO,
))


def ams2_sky_type(raininess: float) -> int:
    """AMS2 rain density to RF2 sky type"""
    if raininess <= 0:
        return 1  # 1 Light Clouds
    if raininess < 0.1:
        return 5  # 5 Cloudy & Drizzle
    if raininess < 0.3:
        return 7  # 7 Overcast & Light Rain
    if raininess < 0.6:
        return 8  # 8 Overcast & Rain
    if raininess < 0.9:
        return 9  # 9 Overcast & Heavy Rain
    return 10  # 10 Overcast & Storm


def ams2_tyre_pressure_kpa(data) -> tuple[float, ...]:
    """Convert AMS2 tyre air pressure to kPa

    Unit is documented as PSI, auto detect unit by value range to avoid conversion error:
    bar (< 6), psi (< 70), otherwise kPa.
    """
    max_pressure = max(data)
    if max_pressure < 6:
        scale = 100.0
    elif max_pressure < 70:
        scale = 6.89475729
    else:
        scale = 1.0
    return (
        rmnan(data[0] * scale),
        rmnan(data[1] * scale),
        rmnan(data[2] * scale),
        rmnan(data[3] * scale),
    )


class DataAdapter:
    """Read & sort data into groups"""

    __slots__ = (
        "shmm",
    )

    def __init__(self, shmm: AMS2Info) -> None:
        """Initialize API setting

        Args:
            shmm: shared memory API data.
        """
        self.shmm = shmm

    def is_player_index(self, index: int | None) -> bool:
        """Is index pointing to player (None or player index)"""
        return index is None or index == self.shmm.playerIndex

    def index_of(self, index: int | None) -> int:
        """Get valid participant index"""
        if index is None:
            return self.shmm.playerIndex
        if 0 <= index < MAX_PARTICIPANTS:
            return index
        return 0


class State(_reader.State, DataAdapter):
    """State"""

    __slots__ = ()

    def active(self) -> bool:
        """Is active (driving or overriding)"""
        return self.shmm.isActive

    def paused(self) -> bool:
        """Is paused"""
        return self.shmm.isPaused

    def resets(self) -> int:
        """Number of player vehicle resets"""
        return self.shmm.vehicleResets

    def version(self) -> str:
        """Identify API version"""
        data = self.shmm.ams2Data
        if data.mVersion:
            return f"{data.mVersion}.{data.mBuildVersionNumber}"
        return DATA.TEXT_NA


class Brake(_reader.Brake, DataAdapter):
    """Brake"""

    __slots__ = ()

    def compound_name(self, index: int | None = None) -> tuple[str, str]:
        """Brake compound name, front, rear"""
        return "", ""

    def bias_front(self, index: int | None = None) -> float:
        """Brake bias front (fraction), AMS2 reports rear bias"""
        bias = self.shmm.ams2Data.mBrakeBias
        if bias < 0:
            return 0.0
        return rmnan(1 - bias)

    def migration(self, index: int | None = None) -> float:
        """Brake migration (percent)"""
        return 0.0

    def pressure(self, index: int | None = None, scale: float = 1) -> tuple[float, ...]:
        """Brake pressure (fraction), estimated from brake input"""
        brake = rmnan(self.shmm.ams2Data.mBrake) * scale
        return brake, brake, brake, brake

    def temperature(self, index: int | None = None) -> tuple[float, ...]:
        """Brake temperature (Celsius)"""
        data = self.shmm.ams2Data.mBrakeTempCelsius
        return (
            rmnan(data[0]),
            rmnan(data[1]),
            rmnan(data[2]),
            rmnan(data[3]),
        )

    def wear(self, index: int | None = None) -> tuple[float, ...]:
        """Brake remaining thickness (meters)"""
        return DATA.WHEELS_NA


class ElectricMotor(_reader.ElectricMotor, DataAdapter):
    """Electric motor"""

    __slots__ = ()

    def state(self, index: int | None = None) -> int:
        """Motor state, 0 = n/a, 1 = off, 2 = drain, 3 = regen

        AMS2 only reports boost (push-to-pass or KERS), active boost is used as drain state.
        """
        if not self.is_player_index(index):
            return 0
        data = self.shmm.ams2Data
        if data.mBoostActive:
            return 2
        if data.mBoostAmount > 0:
            return 1
        return 0

    def battery_charge(self, index: int | None = None) -> float:
        """Battery charge (fraction), remaining boost amount"""
        if not self.is_player_index(index):
            return 0.0
        return min(max(rmnan(self.shmm.ams2Data.mBoostAmount) * 0.01, 0.0), 1.0)

    def rpm(self, index: int | None = None) -> float:
        """Motor RPM (rev per minute)"""
        return 0.0

    def torque(self, index: int | None = None) -> float:
        """Motor torque (Nm)"""
        return 0.0

    def motor_temperature(self, index: int | None = None) -> float:
        """Motor temperature (Celsius)"""
        return 0.0

    def water_temperature(self, index: int | None = None) -> float:
        """Motor water temperature (Celsius)"""
        return 0.0

    def regeneration_level(self, index: int | None = None) -> float:
        """Regeneration level (kW)"""
        return 0.0


class Engine(_reader.Engine, DataAdapter):
    """Engine"""

    __slots__ = ()

    def gear(self, index: int | None = None) -> int:
        """Gear"""
        return self.shmm.ams2Data.mGear

    def gear_max(self, index: int | None = None) -> int:
        """Max gear"""
        return max(self.shmm.ams2Data.mNumGears, 0)

    def rpm(self, index: int | None = None) -> float:
        """RPM (rev per minute)"""
        return rmnan(self.shmm.ams2Data.mRpm)

    def rpm_max(self, index: int | None = None) -> float:
        """Max RPM (rev per minute)"""
        return rmnan(self.shmm.ams2Data.mMaxRPM)

    def torque(self, index: int | None = None) -> float:
        """Torque (Nm)"""
        return rmnan(self.shmm.ams2Data.mEngineTorque)

    def turbo(self, index: int | None = None) -> float:
        """Turbo pressure (Pa)

        Documented as fraction but observed as Pa, unset = -1.
        """
        return max(rmnan(self.shmm.ams2Data.mTurboBoostPressure), 0.0)

    def oil_temperature(self, index: int | None = None) -> float:
        """Oil temperature (Celsius)"""
        return rmnan(self.shmm.ams2Data.mOilTempCelsius)

    def water_temperature(self, index: int | None = None) -> float:
        """Water temperature (Celsius)"""
        return rmnan(self.shmm.ams2Data.mWaterTempCelsius)

    def exhaust_temperature(self, index: int | None = None) -> float:
        """Exhaust temperature (Celsius)"""
        return 0.0

    def lift_and_coast_progress(self, index: int | None = None) -> float:
        """Lift and coast progress (fraction), range 0.0 to 1.0"""
        return 0.0

    def fuel(self, index: int | None = None) -> float:
        """Remaining fuel (liters)"""
        if self.is_player_index(index):
            data = self.shmm.ams2Data
            return rmnan(data.mFuelLevel * data.mFuelCapacity)
        return 0.0

    def fuel_fraction(self, index: int | None = None) -> float:
        """Remaining fuel (fraction)"""
        if self.is_player_index(index):
            return rmnan(self.shmm.ams2Data.mFuelLevel)
        return 0.0

    def tank_capacity(self, index: int | None = None) -> float:
        """Fuel tank capacity (liters)"""
        if self.is_player_index(index):
            return rmnan(self.shmm.ams2Data.mFuelCapacity)
        return 0.0

    def virtual_energy(self, index: int | None = None) -> float:
        """Remaining virtual energy (fraction)"""
        return 0.0

    def max_virtual_energy(self) -> float:
        """Maximum virtual energy (joule)"""
        return 0.0

    def absolute_refill(self) -> float:
        """Absolute refill fuel (liter) or virtual energy (percent)"""
        return 0.0


class Inputs(_reader.Inputs, DataAdapter):
    """Inputs"""

    __slots__ = ()

    def throttle(self, index: int | None = None) -> float:
        """Throttle filtered (fraction)"""
        return rmnan(self.shmm.ams2Data.mThrottle)

    def throttle_raw(self, index: int | None = None) -> float:
        """Throttle raw (fraction), only available for player"""
        if not self.is_player_index(index):
            return 0.0
        return rmnan(self.shmm.ams2Data.mUnfilteredThrottle)

    def brake(self, index: int | None = None) -> float:
        """Brake filtered (fraction)"""
        return rmnan(self.shmm.ams2Data.mBrake)

    def brake_raw(self, index: int | None = None) -> float:
        """Brake raw (fraction), only available for player"""
        if not self.is_player_index(index):
            return 0.0
        return rmnan(self.shmm.ams2Data.mUnfilteredBrake)

    def clutch(self, index: int | None = None) -> float:
        """Clutch filtered (fraction)"""
        return rmnan(self.shmm.ams2Data.mClutch)

    def clutch_raw(self, index: int | None = None) -> float:
        """Clutch raw (fraction), only available for player"""
        if not self.is_player_index(index):
            return 0.0
        return rmnan(self.shmm.ams2Data.mUnfilteredClutch)

    def steering(self, index: int | None = None) -> float:
        """Steering (fraction)"""
        return rmnan(self.shmm.ams2Data.mSteering)

    def steering_range(self, index: int | None = None) -> float:
        """Steering physical rotation range (degrees), not available"""
        return 0.0

    def force_feedback(self) -> float:
        """Steering force feedback (fraction)"""
        return 0.0


class Lap(_reader.Lap, DataAdapter):
    """Lap"""

    __slots__ = ()

    def completed(self, index: int | None = None) -> int:
        """Total completed laps"""
        return self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mLapsCompleted

    def track_length(self) -> float:
        """Full lap or track length (meters)"""
        return rmnan(self.shmm.ams2Data.mTrackLength)

    def distance(self, index: int | None = None) -> float:
        """Distance into lap (meters)"""
        return rmnan(self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mCurrentLapDistance)

    def progress(self, index: int | None = None) -> float:
        """Lap progress (fraction), distance into lap"""
        data = self.shmm.ams2Data
        return rmnan(lap_progress_distance(
            data.mParticipantInfo[self.index_of(index)].mCurrentLapDistance,
            data.mTrackLength,
        ))

    def maximum(self) -> int:
        """Maximum lap"""
        laps = self.shmm.ams2Data.mLapsInEvent
        if laps > 0:
            return laps
        return DATA.MAX_LAPS

    def remaining(self, index: int | None = None) -> float:
        """Remaining lap, count from current lap progress"""
        data = self.shmm.ams2Data
        if data.mLapsInEvent <= 0:
            return 0.0
        laps_left = rmnan(data.mLapsInEvent - self.completed(index) - self.progress(index))
        if laps_left < 0:
            laps_left = 0.0
        return laps_left

    def sector_index(self, index: int | None = None) -> int:
        """Sector index, 0 = S1, 1 = S2, 2 = S3"""
        sector = self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mCurrentSector
        if sector <= 0:
            return 0
        if sector == 1:
            return 1
        return 2

    def safety_car_distance(self) -> float:
        """Safety car's distance into lap (meters)"""
        return 0.0

    def safety_car_active(self) -> bool:
        """Is safety car (full course yellow) active on track"""
        return self.shmm.ams2Data.mYellowFlagState > YellowFlagState.NONE


class Session(_reader.Session, DataAdapter):
    """Session"""

    __slots__ = ()

    def combo_name(self) -> str:
        """Track & vehicle combo name, strip off invalid char"""
        class_name = tostr(self.shmm.ams2Data.mCarClassName)
        return strip_invalid_char(f"{self.track_name()} - {class_name}")

    def track_name(self) -> str:
        """Track name, strip off invalid char"""
        data = self.shmm.ams2Data
        location = tostr(data.mTrackLocation)
        variation = tostr(data.mTrackVariation)
        if variation:
            return strip_invalid_char(f"{location} {variation}")
        return strip_invalid_char(location)

    def identifier(self) -> tuple[int, int, int]:
        """Identify session"""
        data = self.shmm.ams2Data
        session_stamp = int(self.shmm.vehicleResets * 100 + data.mSessionState)
        session_etime = int(self.shmm.elapsed)
        session_tlaps = data.mParticipantInfo[self.shmm.playerIndex].mLapsCompleted
        return session_stamp, session_etime, session_tlaps

    def elapsed(self) -> float:
        """Session elapsed time (seconds)"""
        return self.shmm.elapsed

    def remaining(self) -> float:
        """Session time remaining (seconds), minimum limit to 0"""
        data = self.shmm.ams2Data
        seconds = data.mEventTimeRemaining
        if seconds <= 0:
            return 0.0
        # Documented as milliseconds but observed as seconds, convert only if out of range
        if seconds > data.mSessionDuration * 60 + 60:
            seconds *= 0.001
        return rmnan(seconds)

    def session_type(self) -> int:
        """Session type, 0 = TESTDAY, 1 = PRACTICE, 2 = QUALIFY, 3 = WARMUP, 4 = RACE, 5 = HOTLAP"""
        session = self.shmm.ams2Data.mSessionState
        if session in (SessionState.RACE, SessionState.FORMATION_LAP):
            return 4
        if session == SessionState.QUALIFY:
            return 2
        if session == SessionState.PRACTICE:
            return 1
        if session == SessionState.TIME_ATTACK:
            return 5
        return 0  # test day

    def finish_type(self, as_lap: bool | None = None) -> int:
        """Race finish type, 0 = time, 1 = laps only, 2 = laps & time"""
        data = self.shmm.ams2Data
        if data.mSessionDuration <= 0:
            return 1  # laps only
        return 0  # time only (plus mSessionAdditionalLaps after time expired)

    def in_race(self) -> bool:
        """Is in race session"""
        return self.shmm.ams2Data.mSessionState in (SessionState.RACE, SessionState.FORMATION_LAP)

    def private_qualifying(self) -> bool:
        """Is private qualifying"""
        return self.shmm.ams2Data.mSessionIsPrivate

    def pit_open(self) -> bool:
        """Is pit lane open"""
        return self.shmm.ams2Data.mYellowFlagState not in (
            YellowFlagState.PENDING,
            YellowFlagState.PITS_CLOSED,
        )

    def pre_race(self) -> bool:
        """Before race starts (green flag)"""
        data = self.shmm.ams2Data
        return self.in_race() and data.mRaceState <= RaceState.NOT_STARTED

    def green_flag(self) -> bool:
        """Green flag (race starts)"""
        data = self.shmm.ams2Data
        return self.in_race() and data.mRaceState >= RaceState.RACING

    def blue_flag(self, index: int | None = None) -> bool:
        """Is under blue flag"""
        return self.shmm.ams2Data.mHighestFlagColours[self.index_of(index)] == FlagColour.BLUE

    def yellow_flag(self) -> bool:
        """Is there yellow flag in any sectors"""
        data = self.shmm.ams2Data
        return (
            data.mHighestFlagColour in (FlagColour.YELLOW, FlagColour.DOUBLE_YELLOW)
            or data.mYellowFlagState > YellowFlagState.NONE
        )

    def start_lights(self) -> int:
        """Start lights countdown sequence, 0=green flag, -1=no start lights"""
        return -1

    def track_temperature(self) -> float:
        """Track temperature (Celsius)"""
        return rmnan(self.shmm.ams2Data.mTrackTemperature)

    def ambient_temperature(self) -> float:
        """Ambient temperature (Celsius)"""
        return rmnan(self.shmm.ams2Data.mAmbientTemperature)

    def raininess(self) -> float:
        """Rain severity (fraction), range 0.0 - 1.0, snow counts as precipitation"""
        data = self.shmm.ams2Data
        return min(max(rmnan(data.mRainDensity), rmnan(data.mSnowDensity), 0.0), 1.0)

    def wetness(self) -> float:
        """Road wetness set (fraction), not available"""
        return 0.0

    def weather_forecast(self) -> tuple[tuple[float, int, float, float], ...]:
        """Weather forecast nodes, not available"""
        return ()

    def cloud_coverage(self) -> int:
        """Cloud coverage (type index), range 0 to 10"""
        return ams2_sky_type(self.raininess())

    def grip_level(self) -> float:
        """Track base grip level, not available"""
        return 0.0

    def track_time(self, scale: int = 1) -> float:
        """Track time, not available"""
        return 0.0

    def time_scale(self) -> int:
        """Time scale, not available"""
        return 1

    def limits_points(self) -> float:
        """Track limits points per penalty"""
        return 0.0

    def cut_points(self, index: int | None = None) -> float:
        """Current track limits cut points per penalty"""
        return 0.0

    def wind_direction(self) -> float:
        """Wind direction (degrees)"""
        data = self.shmm.ams2Data
        wind_dir = rmnan(atan2(data.mWindDirectionX, data.mWindDirectionY) * 57.29577951308232)
        if wind_dir == 0:
            return 0
        return wind_dir - wind_dir // 360 * 360

    def wind_speed(self) -> float:
        """Wind speed (m/s)"""
        return rmnan(self.shmm.ams2Data.mWindSpeed)


class Switch(_reader.Switch, DataAdapter):
    """Switch"""

    __slots__ = ()

    def tc_level(self, index: int | None = None) -> int:
        """TC level"""
        return self.shmm.ams2Data.mTractionControlSetting

    def tc_cut_level(self, index: int | None = None) -> int:
        """TC cut level"""
        return -1

    def tc_slip_level(self, index: int | None = None) -> int:
        """TC slip level"""
        return -1

    def abs_level(self, index: int | None = None) -> int:
        """ABS level"""
        return self.shmm.ams2Data.mAntiLockSetting

    def motor_map_level(self, index: int | None = None) -> int:
        """Motor or engine map level, ERS deployment mode if available"""
        mode = self.shmm.ams2Data.mErsDeploymentMode
        if mode > 0:
            return mode
        return -1

    def brake_migration_level(self, index: int | None = None) -> int:
        """Brake migration level"""
        return -1

    def front_arb_level(self, index: int | None = None) -> int:
        """Front anti-roll bar level"""
        return -1

    def rear_arb_level(self, index: int | None = None) -> int:
        """Rear anti-roll bar level"""
        return -1

    def wipers(self, index: int | None = None) -> int:
        """Wipers state, 0 = off, 1 = auto, 2 = slow, 3 = fast"""
        return 0

    def headlights(self, index: int | None = None) -> int:
        """Headlights"""
        return int(self.shmm.ams2Data.mCarFlags & CarFlags.HEADLIGHT > 0)

    def ignition(self, index: int | None = None, stall_rpm: float = 100) -> int:
        """Ignition, 0=engine off, 1=ignition on, 2=engine on"""
        data = self.shmm.ams2Data
        if data.mCarFlags & CarFlags.ENGINE_ACTIVE:
            if data.mRpm > stall_rpm:
                return 2
            return 1
        return 0

    def speed_limiter(self, index: int | None = None) -> int:
        """Speed limiter"""
        return int(self.shmm.ams2Data.mCarFlags & CarFlags.SPEED_LIMITER > 0)

    def tc_active(self, index: int | None = None) -> bool:
        """TC activation state"""
        return self.shmm.ams2Data.mCarFlags & CarFlags.TCS > 0

    def abs_active(self, index: int | None = None) -> bool:
        """ABS activation state"""
        data = self.shmm.ams2Data
        return data.mAntiLockActive or data.mCarFlags & CarFlags.ABS > 0

    def drs_status(self, index: int | None = None) -> int:
        """DRS status, 0 not_available, 1 available, 2 allowed(not activated), 3 activated"""
        state = self.shmm.ams2Data.mDrsState
        if not state & DrsState.INSTALLED:
            return 0
        if state & DrsState.ACTIVE:
            return 3
        if not state & DrsState.ZONE_RULES or state & DrsState.AVAILABLE_NOW:
            return 2
        if state & DrsState.AVAILABLE_NEXT:
            return 1
        return 0

    def auto_clutch(self) -> bool:
        """Auto clutch"""
        return False


class Timing(_reader.Timing, DataAdapter):
    """Timing"""

    __slots__ = ()

    def elapsed(self, index: int | None = None) -> float:
        """Current elapsed time (seconds)"""
        return self.shmm.elapsed

    def is_last_valid(self, index: int | None = None) -> bool:
        """Is last lap time valid"""
        return self.shmm.ams2Tracker.last_valid[self.index_of(index)]

    def current_laptime(self, index: int | None = None) -> float:
        """Current lap time (seconds)"""
        if self.is_player_index(index):
            return max(rmnan(self.shmm.ams2Data.mCurrentTime), 0.0)
        return max(self.shmm.elapsed - self.shmm.ams2Tracker.lap_start[self.index_of(index)], 0.0)

    def last_laptime(self, index: int | None = None) -> float:
        """Last lap time (seconds), positive=valid, negative=invalid"""
        index = self.index_of(index)
        last = max(rmnan(self.shmm.ams2Data.mLastLapTimes[index]), 0.0)
        if self.shmm.ams2Tracker.last_valid[index]:
            return last
        return -last

    def best_laptime(self, index: int | None = None) -> float:
        """Best lap time (seconds)"""
        return max(rmnan(self.shmm.ams2Data.mFastestLapTimes[self.index_of(index)]), 0.0)

    def reference_laptime(self, index: int | None = None, laptime: float = 0) -> float:
        """Reference lap time (seconds)"""
        if 0 < laptime < DATA.MAX_SECONDS:
            return laptime
        init_time = min_nonzero((
            self.best_laptime(index),
            abs(self.last_laptime(index)),
            DATA.MAX_SECONDS,
        ))
        if 0 < init_time < DATA.MAX_SECONDS:
            return init_time
        # Set to estimated laptime only if other laptime not available
        # as estimated laptime can be faster than other laptime
        return min_nonzero((
            self.estimated_laptime(index),
            DATA.MAX_SECONDS,
        ))

    def estimated_laptime(self, index: int | None = None) -> float:
        """Estimated lap time (seconds)

        Use player reference lap time for all vehicles,
        so that relative time gaps share same time scale.
        """
        init_time = min_nonzero((
            self.best_laptime(),
            abs(self.last_laptime()),
            DATA.MAX_SECONDS,
        ))
        if 0 < init_time < DATA.MAX_SECONDS:
            return init_time
        return rmnan(self.shmm.ams2Data.mTrackLength / 40)

    def estimated_time_into(self, index: int | None = None) -> float:
        """Estimated time into lap (seconds)"""
        data = self.shmm.ams2Data
        progress = lap_progress_distance(
            data.mParticipantInfo[self.index_of(index)].mCurrentLapDistance,
            data.mTrackLength,
        )
        return rmnan(self.estimated_laptime() * progress)

    def last_sector(self, index: int | None = None) -> float:
        """Last sector time (seconds)"""
        return self.shmm.ams2LastSectorTime.last


class Tyre(_reader.Tyre, DataAdapter):
    """Tyre (front left, front right, rear left, rear right)"""

    __slots__ = ()

    def compound_name(self, index: int | None = None) -> tuple[str, ...]:
        """Tyre compound name set"""
        if self.is_player_index(index):
            data = self.shmm.ams2Data.mTyreCompound
            return (
                tostr(data[0].value),
                tostr(data[1].value),
                tostr(data[2].value),
                tostr(data[3].value),
            )
        return "", "", "", ""

    def compound_class(self, index: int | None = None) -> tuple[str, ...]:
        """Tyre compound name set with class name prefix"""
        if self.is_player_index(index):
            class_name = tostr(self.shmm.ams2Data.mCarClassName)
            return tuple(
                f"{class_name} - {compound}" if compound else ""
                for compound in self.compound_name()
            )
        return "", "", "", ""

    def surface_temperature_avg(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre surface temperature set (Celsius) average"""
        data = self.shmm.ams2Data
        left = data.mTyreTempLeft
        center = data.mTyreTempCenter
        right = data.mTyreTempRight
        return (
            rmnan((left[0] + center[0] + right[0]) / 3),
            rmnan((left[1] + center[1] + right[1]) / 3),
            rmnan((left[2] + center[2] + right[2]) / 3),
            rmnan((left[3] + center[3] + right[3]) / 3),
        )

    def surface_temperature_ico(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre surface temperature set (Celsius) left,center,right"""
        data = self.shmm.ams2Data
        left = data.mTyreTempLeft
        center = data.mTyreTempCenter
        right = data.mTyreTempRight
        return (
            rmnan(left[0]), rmnan(center[0]), rmnan(right[0]),
            rmnan(left[1]), rmnan(center[1]), rmnan(right[1]),
            rmnan(left[2]), rmnan(center[2]), rmnan(right[2]),
            rmnan(left[3]), rmnan(center[3]), rmnan(right[3]),
        )

    def inner_temperature_avg(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre inner temperature set (Celsius) average"""
        data = self.shmm.ams2Data.mTyreLayerTemp
        return (
            rmnan(data[0]) + KELVIN_TO_CELSIUS,
            rmnan(data[1]) + KELVIN_TO_CELSIUS,
            rmnan(data[2]) + KELVIN_TO_CELSIUS,
            rmnan(data[3]) + KELVIN_TO_CELSIUS,
        )

    def inner_temperature_ico(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre inner temperature set (Celsius) inner,center,outer"""
        front_left, front_right, rear_left, rear_right = self.inner_temperature_avg()
        return (
            front_left, front_left, front_left,
            front_right, front_right, front_right,
            rear_left, rear_left, rear_left,
            rear_right, rear_right, rear_right,
        )

    def pressure(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre pressure (kPa)"""
        return ams2_tyre_pressure_kpa(self.shmm.ams2Data.mAirPressure)

    def load(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre load (Newtons)"""
        return DATA.WHEELS_ZERO

    def wear(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre wear (fraction), remaining tread"""
        data = self.shmm.ams2Data.mTyreWear
        return (
            rmnan(1 - data[0]),
            rmnan(1 - data[1]),
            rmnan(1 - data[2]),
            rmnan(1 - data[3]),
        )

    def puncture(self, index: int | None = None, threshold: float = 1) -> tuple[bool, ...]:
        """Tyre puncture state"""
        data = self.shmm.ams2Data.mTyreFlags
        return (
            not data[0] & TyreFlags.INFLATED,
            not data[1] & TyreFlags.INFLATED,
            not data[2] & TyreFlags.INFLATED,
            not data[3] & TyreFlags.INFLATED,
        )

    def carcass_temperature(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre carcass temperature (Celsius)"""
        data = self.shmm.ams2Data.mTyreCarcassTemp
        return (
            rmnan(data[0]) + KELVIN_TO_CELSIUS,
            rmnan(data[1]) + KELVIN_TO_CELSIUS,
            rmnan(data[2]) + KELVIN_TO_CELSIUS,
            rmnan(data[3]) + KELVIN_TO_CELSIUS,
        )

    def vertical_deflection(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre vertical deflection (millimeters)"""
        return 1, 1, 1, 1

    def slip_angle(self, index: int | None = None) -> tuple[float, ...]:
        """Tyre slip angle (radians)"""
        return DATA.WHEELS_ZERO


class Vehicle(_reader.Vehicle, DataAdapter):
    """Vehicle"""

    __slots__ = ()

    def incidents(self, index: int | None = None) -> int:
        """Number of incidents"""
        return 0

    def is_player(self, index: int = 0) -> bool:
        """Is local player"""
        return self.shmm.playerIndex == index

    def is_driving(self) -> bool:
        """Is local player driving or in monitor"""
        return self.shmm.ams2Data.mMaxRPM > 0

    def player_index(self) -> int:
        """Get Local player index"""
        return self.shmm.playerIndex

    def slot_id(self, index: int | None = None) -> int:
        """Vehicle slot id"""
        return self.index_of(index)

    def driver_name(self, index: int | None = None) -> str:
        """Driver name"""
        return tostr(self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mName)

    def team_name(self, index: int | None = None) -> str:
        """Team name"""
        return ""

    def vehicle_model(self, index: int | None = None) -> str:
        """Vehicle model name"""
        return tostr(self.shmm.ams2Data.mCarNames[self.index_of(index)].value)

    def class_name(self, index: int | None = None) -> str:
        """Vehicle class name"""
        return tostr(self.shmm.ams2Data.mCarClassNames[self.index_of(index)].value)

    def same_class(self, index: int | None = None) -> bool:
        """Is same vehicle class"""
        class_names = self.shmm.ams2Data.mCarClassNames
        return class_names[self.index_of(index)].value == class_names[self.shmm.playerIndex].value

    def total_vehicles(self) -> int:
        """Total vehicles"""
        return min(max(self.shmm.ams2Data.mNumParticipants, 0), MAX_PARTICIPANTS)

    def place(self, index: int | None = None) -> int:
        """Vehicle overall place"""
        return self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mRacePosition

    def qualification(self, index: int | None = None) -> int:
        """Vehicle qualification place, use starting grid position if recorded"""
        index = self.index_of(index)
        grid = self.shmm.ams2Tracker.grid[index]
        if grid > 0:
            return grid
        return self.shmm.ams2Data.mParticipantInfo[index].mRacePosition

    def in_pits(self, index: int | None = None) -> bool:
        """Is in pits"""
        return self.shmm.ams2Data.mPitModes[self.index_of(index)] != PitMode.NONE

    def in_garage(self, index: int | None = None) -> bool:
        """Is in garage"""
        return self.shmm.ams2Data.mPitModes[self.index_of(index)] in (
            PitMode.IN_GARAGE,
            PitMode.DRIVING_OUT_OF_GARAGE,
        )

    def in_paddock(self, index: int | None = None) -> int:
        """Is in paddock (either pit lane or garage), 0 = on track, 1 = pit lane, 2 = garage"""
        if self.in_garage(index):
            return 2
        return int(self.in_pits(index))

    def number_pitstops(self, index: int | None = None, penalty: int = 0) -> int:
        """Number of pit stops"""
        return -penalty if penalty else self.shmm.ams2Tracker.pitstops[self.index_of(index)]

    def number_penalties(self, index: int | None = None) -> int:
        """Number of penalties"""
        return int(self.shmm.ams2Data.mPitSchedules[self.index_of(index)] in PIT_PENALTY)

    def pit_request(self, index: int | None = None) -> bool:
        """Is requested pit"""
        return self.shmm.ams2Data.mPitSchedules[self.index_of(index)] in PIT_REQUESTED

    def pit_stop_time(self) -> float:
        """Estimated pit stop time (seconds)"""
        return 0.0

    def repair_time(self) -> float:
        """Scheduled repair time (seconds)"""
        return 0.0

    def finish_state(self, index: int | None = None) -> int:
        """Finish state, 0 = none, 1 = finished, 2 = DNF, 3 = DQ"""
        state = self.shmm.ams2Data.mRaceStates[self.index_of(index)]
        if state == RaceState.FINISHED:
            return 1
        if state in (RaceState.DNF, RaceState.RETIRED):
            return 2
        if state == RaceState.DISQUALIFIED:
            return 3
        return 0

    def orientation_yaw(self, index: int | None = None) -> float:
        """Orientation yaw (radians)"""
        return -rmnan(self.shmm.ams2Data.mOrientations[self.index_of(index)][1])  # in AMS2 coord system

    def position_xyz(self, index: int | None = None) -> tuple[float, float, float]:
        """Raw x,y,z position (meters)"""
        pos = self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mWorldPosition
        return rmnan(pos[0]), rmnan(pos[1]), rmnan(pos[2])

    def position_longitudinal(self, index: int | None = None) -> float:
        """Longitudinal axis position (meters) related to world plane"""
        return rmnan(self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mWorldPosition[0])

    def position_lateral(self, index: int | None = None) -> float:
        """Lateral axis position (meters) related to world plane"""
        return -rmnan(self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mWorldPosition[2])  # in AMS2 coord system

    def position_vertical(self, index: int | None = None) -> float:
        """Vertical axis position (meters) related to world plane"""
        return rmnan(self.shmm.ams2Data.mParticipantInfo[self.index_of(index)].mWorldPosition[1])

    def acceleration_lateral(self, index: int | None = None) -> float:
        """Lateral acceleration (m/s^2)"""
        return rmnan(self.shmm.ams2Data.mLocalAcceleration[0])

    def acceleration_longitudinal(self, index: int | None = None) -> float:
        """Longitudinal acceleration (m/s^2)"""
        return rmnan(self.shmm.ams2Data.mLocalAcceleration[2])

    def acceleration_vertical(self, index: int | None = None) -> float:
        """Vertical acceleration (m/s^2)"""
        return rmnan(self.shmm.ams2Data.mLocalAcceleration[1])

    def velocity_lateral(self, index: int | None = None) -> float:
        """Lateral velocity (m/s) x"""
        return rmnan(self.shmm.ams2Data.mLocalVelocity[0])

    def velocity_longitudinal(self, index: int | None = None) -> float:
        """Longitudinal velocity (m/s) y"""
        return rmnan(self.shmm.ams2Data.mLocalVelocity[2])

    def velocity_vertical(self, index: int | None = None) -> float:
        """Vertical velocity (m/s) z"""
        return rmnan(self.shmm.ams2Data.mLocalVelocity[1])

    def speed(self, index: int | None = None) -> float:
        """Speed (m/s)"""
        if index is None:
            return rmnan(self.shmm.ams2Data.mSpeed)
        return rmnan(self.shmm.ams2Data.mSpeeds[self.index_of(index)])

    def downforce_front(self, index: int | None = None) -> float:
        """Downforce front (Newtons)"""
        return 0.0

    def downforce_rear(self, index: int | None = None) -> float:
        """Downforce rear (Newtons)"""
        return 0.0

    def damage_severity(self, index: int | None = None) -> tuple[float, ...]:
        """Damage severity, sort row by row from left to right, top to bottom

        AMS2 does not provide location based damage, use aero damage for all parts.
        """
        if not self.is_player_index(index):
            return (0.0,) * 8
        damage = rmnan(self.shmm.ams2Data.mAeroDamage * 2)
        return (damage,) * 8

    def aero_damage(self, index: int | None = None) -> float:
        """Aerodynamic damage (fraction), -1.0 unavailable, 0.0 no damage, 1.0 totaled"""
        if not self.is_player_index(index):
            return -1.0
        return rmnan(self.shmm.ams2Data.mAeroDamage)

    def integrity(self, index: int | None = None) -> float:
        """Vehicle integrity, only available for player"""
        if not self.is_player_index(index):
            return 1.0
        data = self.shmm.ams2Data
        return rmnan(1 - max(data.mAeroDamage, data.mEngineDamage))

    def is_detached(self, index: int | None = None) -> bool:
        """Whether any vehicle parts are detached"""
        return False

    def impact_time(self, index: int | None = None) -> float:
        """Last impact time stamp (seconds)"""
        return self.shmm.ams2LastImpactTime

    def impact_position(self, index: int | None = None) -> tuple[float, float]:
        """Last impact position x,y coordinates"""
        return 0.0, 0.0

    def setup(self) -> tuple[str, ...]:
        """Car setup data"""
        return ()


class Wheel(_reader.Wheel, DataAdapter):
    """Wheel & suspension (front left, front right, rear left, rear right)"""

    __slots__ = ()

    def track_front(self, index: int | None = None) -> float:
        """Wheel track front (millimeters)"""
        return 0.0

    def track_rear(self, index: int | None = None) -> float:
        """Wheel track rear (millimeters)"""
        return 0.0

    def wheelbase(self, index: int | None = None) -> float:
        """Wheelbase (millimeters)"""
        return 0.0

    def camber(self, index: int | None = None) -> tuple[float, ...]:
        """Wheel camber (radians)"""
        return DATA.WHEELS_ZERO

    def toe(self, index: int | None = None) -> tuple[float, ...]:
        """Wheel toe (radians)"""
        return DATA.WHEELS_ZERO

    def rotation(self, index: int | None = None) -> tuple[float, ...]:
        """Wheel rotation (radians per second), or angular velocity

        Convert to RF2 sign convention (negative while moving forward).
        """
        data = self.shmm.ams2Data.mTyreRPS
        return (
            -abs(rmnan(data[0])) * TAU,
            -abs(rmnan(data[1])) * TAU,
            -abs(rmnan(data[2])) * TAU,
            -abs(rmnan(data[3])) * TAU,
        )

    def ride_height(self, index: int | None = None) -> tuple[float, ...]:
        """Ride height (convert centimeters to millimeters)"""
        data = self.shmm.ams2Data.mRideHeight
        return (
            rmnan(data[0]) * 10,
            rmnan(data[1]) * 10,
            rmnan(data[2]) * 10,
            rmnan(data[3]) * 10,
        )

    def third_spring_deflection(self, index: int | None = None) -> tuple[float, ...]:
        """Third spring deflection front & rear (convert meters to millimeters)"""
        data = self.shmm.ams2Data.mSuspensionTravel
        front = rmnan((data[0] + data[1]) * 500)
        rear = rmnan((data[2] + data[3]) * 500)
        return front, front, rear, rear

    def suspension_deflection(self, index: int | None = None) -> tuple[float, ...]:
        """Suspension deflection (convert meters to millimeters)"""
        data = self.shmm.ams2Data.mSuspensionTravel
        return (
            rmnan(data[0]) * 1000,
            rmnan(data[1]) * 1000,
            rmnan(data[2]) * 1000,
            rmnan(data[3]) * 1000,
        )

    def suspension_force(self, index: int | None = None) -> tuple[float, ...]:
        """Suspension force (Newtons)"""
        return DATA.WHEELS_ZERO

    def suspension_damage(self, index: int | None = None) -> tuple[float, ...]:
        """Suspension damage (fraction), 0.0 no damage, 1.0 totaled"""
        data = self.shmm.ams2Data.mSuspensionDamage
        return (
            rmnan(data[0]),
            rmnan(data[1]),
            rmnan(data[2]),
            rmnan(data[3]),
        )

    def position_vertical(self, index: int | None = None) -> tuple[float, ...]:
        """Vertical wheel position (convert meters to millimeters) related to vehicle"""
        data = self.shmm.ams2Data.mWheelLocalPositionY
        return (
            rmnan(data[0]) * 1000,
            rmnan(data[1]) * 1000,
            rmnan(data[2]) * 1000,
            rmnan(data[3]) * 1000,
        )

    def is_detached(self, index: int | None = None) -> tuple[bool, ...]:
        """Whether wheel is detached"""
        data = self.shmm.ams2Data.mTyreFlags
        return (
            not data[0] & TyreFlags.ATTACHED,
            not data[1] & TyreFlags.ATTACHED,
            not data[2] & TyreFlags.ATTACHED,
            not data[3] & TyreFlags.ATTACHED,
        )

    def offroad(self, index: int | None = None) -> int:
        """Number of wheels currently off the road"""
        return sum(terrain in TERRAIN_OFFROAD for terrain in self.shmm.ams2Data.mTerrain)
