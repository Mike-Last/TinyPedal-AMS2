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
AMS2 sharedmemory data structure

Based on Automobilista 2 "SharedMemory.h" (SHARED_MEMORY_VERSION 14),
located in game folder "Support/SharedMemory".
"""

import ctypes

c_bool = ctypes.c_bool
c_char = ctypes.c_char
c_float = ctypes.c_float
c_int = ctypes.c_int
c_uint = ctypes.c_uint


class AMS2Constants:
    """AMS2 constants"""

    MM_FILE_NAME = "$pcars2$"
    SHARED_MEMORY_VERSION = 14
    STRING_LENGTH_MAX = 64
    STORED_PARTICIPANTS_MAX = 64
    TYRE_COMPOUND_NAME_LENGTH_MAX = 40
    TYRE_MAX = 4
    VEC_MAX = 3
    INVALID_INDEX = -1


class GameState:
    """Game state (mGameState)"""

    EXITED = 0
    FRONT_END = 1
    INGAME_PLAYING = 2
    INGAME_PAUSED = 3
    INGAME_INMENU_TIME_TICKING = 4
    INGAME_RESTARTING = 5
    INGAME_REPLAY = 6
    FRONT_END_REPLAY = 7


class SessionState:
    """Session state (mSessionState)"""

    INVALID = 0
    PRACTICE = 1
    TEST = 2
    QUALIFY = 3
    FORMATION_LAP = 4
    RACE = 5
    TIME_ATTACK = 6


class RaceState:
    """Race state (mRaceState, mRaceStates)"""

    INVALID = 0
    NOT_STARTED = 1
    RACING = 2
    FINISHED = 3
    DISQUALIFIED = 4
    RETIRED = 5
    DNF = 6


class FlagColour:
    """Flag colour (mHighestFlagColour, mHighestFlagColours)"""

    NONE = 0
    GREEN = 1
    BLUE = 2
    WHITE_SLOW_CAR = 3
    WHITE_FINAL_LAP = 4
    RED = 5
    YELLOW = 6
    DOUBLE_YELLOW = 7
    BLACK_AND_WHITE = 8
    BLACK_ORANGE_CIRCLE = 9
    BLACK = 10
    CHEQUERED = 11


class PitMode:
    """Pit mode (mPitMode, mPitModes)"""

    NONE = 0
    DRIVING_INTO_PITS = 1
    IN_PIT = 2
    DRIVING_OUT_OF_PITS = 3
    IN_GARAGE = 4
    DRIVING_OUT_OF_GARAGE = 5


class PitSchedule:
    """Pit schedule (mPitSchedule, mPitSchedules)"""

    NONE = 0
    PLAYER_REQUESTED = 1
    ENGINEER_REQUESTED = 2
    DAMAGE_REQUESTED = 3
    MANDATORY = 4
    DRIVE_THROUGH = 5
    STOP_GO = 6
    PITSPOT_OCCUPIED = 7


class CarFlags:
    """Car flags bitmask (mCarFlags)"""

    HEADLIGHT = 1 << 0
    ENGINE_ACTIVE = 1 << 1
    ENGINE_WARNING = 1 << 2
    SPEED_LIMITER = 1 << 3
    ABS = 1 << 4
    HANDBRAKE = 1 << 5
    TCS = 1 << 6
    SCS = 1 << 7


class TyreFlags:
    """Tyre flags bitmask (mTyreFlags)"""

    ATTACHED = 1 << 0
    INFLATED = 1 << 1
    IS_ON_GROUND = 1 << 2


class DrsState:
    """DRS state bitmask (mDrsState)"""

    INSTALLED = 1 << 0
    ZONE_RULES = 1 << 1
    AVAILABLE_NEXT = 1 << 2
    AVAILABLE_NOW = 1 << 3
    ACTIVE = 1 << 4


class YellowFlagState:
    """Full course yellow state (mYellowFlagState)"""

    INVALID = -1
    NONE = 0
    PENDING = 1
    PITS_CLOSED = 2
    PIT_LEAD_LAP = 3
    PITS_OPEN = 4
    PITS_OPEN2 = 5
    LAST_LAP = 6
    RESUME = 7
    RACE_HALT = 8


# Terrain material index (mTerrain) considered as off road (or beyond track limits)
TERRAIN_OFFROAD = frozenset((
    6,  # GRASSY_BERMS
    7,  # GRASS
    8,  # GRAVEL
    9,  # BUMPY_GRAVEL
    15,  # SAND
    16,  # BUMPY_SAND
    17,  # DIRT
    18,  # BUMPY_DIRT
    22,  # DIRT_BANK
    24,  # DRY_VERGE
    26,  # GRASSCRETE
    27,  # LONG_GRASS
    28,  # SLOPE_GRASS
    32,  # ASTROTURF
    33,  # SNOWHALF
    34,  # SNOWFULL
    42,  # ROUGH_SAND_MEDIUM
    43,  # ROUGH_SAND_HEAVY
    46,  # RUNOFF_ROAD
    47,  # ILLEGAL_STRIP
    49,  # PAINT_CONCRETE_ILLEGAL
))

_STR = c_char * AMS2Constants.STRING_LENGTH_MAX
_VEC = c_float * AMS2Constants.VEC_MAX
_TYRE_FLOAT = c_float * AMS2Constants.TYRE_MAX
_TYRE_UINT = c_uint * AMS2Constants.TYRE_MAX
_MAX_PART = AMS2Constants.STORED_PARTICIPANTS_MAX


class AMS2ParticipantInfo(ctypes.Structure):
    """Participant info"""

    __slots__ = ()
    _fields_ = [
        ("mIsActive", c_bool),
        ("mName", _STR),
        ("mWorldPosition", _VEC),
        ("mCurrentLapDistance", c_float),
        ("mRacePosition", c_uint),
        ("mLapsCompleted", c_uint),
        ("mCurrentLap", c_uint),
        ("mCurrentSector", c_int),
    ]


class AMS2SharedMemory(ctypes.Structure):
    """AMS2 shared memory"""

    __slots__ = ()
    _fields_ = [
        # Version Number
        ("mVersion", c_uint),
        ("mBuildVersionNumber", c_uint),
        # Game States
        ("mGameState", c_uint),
        ("mSessionState", c_uint),
        ("mRaceState", c_uint),
        # Participant Info
        ("mViewedParticipantIndex", c_int),
        ("mNumParticipants", c_int),
        ("mParticipantInfo", AMS2ParticipantInfo * _MAX_PART),
        # Unfiltered Input
        ("mUnfilteredThrottle", c_float),
        ("mUnfilteredBrake", c_float),
        ("mUnfilteredSteering", c_float),
        ("mUnfilteredClutch", c_float),
        # Vehicle information
        ("mCarName", _STR),
        ("mCarClassName", _STR),
        # Event information
        ("mLapsInEvent", c_uint),
        ("mTrackLocation", _STR),
        ("mTrackVariation", _STR),
        ("mTrackLength", c_float),
        # Timings
        ("mNumSectors", c_int),
        ("mLapInvalidated", c_bool),
        ("mBestLapTime", c_float),
        ("mLastLapTime", c_float),
        ("mCurrentTime", c_float),
        ("mSplitTimeAhead", c_float),
        ("mSplitTimeBehind", c_float),
        ("mSplitTime", c_float),
        ("mEventTimeRemaining", c_float),
        ("mPersonalFastestLapTime", c_float),
        ("mWorldFastestLapTime", c_float),
        ("mCurrentSector1Time", c_float),
        ("mCurrentSector2Time", c_float),
        ("mCurrentSector3Time", c_float),
        ("mFastestSector1Time", c_float),
        ("mFastestSector2Time", c_float),
        ("mFastestSector3Time", c_float),
        ("mPersonalFastestSector1Time", c_float),
        ("mPersonalFastestSector2Time", c_float),
        ("mPersonalFastestSector3Time", c_float),
        ("mWorldFastestSector1Time", c_float),
        ("mWorldFastestSector2Time", c_float),
        ("mWorldFastestSector3Time", c_float),
        # Flags
        ("mHighestFlagColour", c_uint),
        ("mHighestFlagReason", c_uint),
        # Pit Info
        ("mPitMode", c_uint),
        ("mPitSchedule", c_uint),
        # Car State
        ("mCarFlags", c_uint),
        ("mOilTempCelsius", c_float),
        ("mOilPressureKPa", c_float),
        ("mWaterTempCelsius", c_float),
        ("mWaterPressureKPa", c_float),
        ("mFuelPressureKPa", c_float),
        ("mFuelLevel", c_float),
        ("mFuelCapacity", c_float),
        ("mSpeed", c_float),
        ("mRpm", c_float),
        ("mMaxRPM", c_float),
        ("mBrake", c_float),
        ("mThrottle", c_float),
        ("mClutch", c_float),
        ("mSteering", c_float),
        ("mGear", c_int),
        ("mNumGears", c_int),
        ("mOdometerKM", c_float),
        ("mAntiLockActive", c_bool),
        ("mLastOpponentCollisionIndex", c_int),
        ("mLastOpponentCollisionMagnitude", c_float),
        ("mBoostActive", c_bool),
        ("mBoostAmount", c_float),
        # Motion & Device Related
        ("mOrientation", _VEC),
        ("mLocalVelocity", _VEC),
        ("mWorldVelocity", _VEC),
        ("mAngularVelocity", _VEC),
        ("mLocalAcceleration", _VEC),
        ("mWorldAcceleration", _VEC),
        ("mExtentsCentre", _VEC),
        # Wheels / Tyres
        ("mTyreFlags", _TYRE_UINT),
        ("mTerrain", _TYRE_UINT),
        ("mTyreY", _TYRE_FLOAT),
        ("mTyreRPS", _TYRE_FLOAT),
        ("mTyreSlipSpeed", _TYRE_FLOAT),  # obsolete
        ("mTyreTemp", _TYRE_FLOAT),
        ("mTyreGrip", _TYRE_FLOAT),  # obsolete
        ("mTyreHeightAboveGround", _TYRE_FLOAT),
        ("mTyreLateralStiffness", _TYRE_FLOAT),  # obsolete
        ("mTyreWear", _TYRE_FLOAT),
        ("mBrakeDamage", _TYRE_FLOAT),
        ("mSuspensionDamage", _TYRE_FLOAT),
        ("mBrakeTempCelsius", _TYRE_FLOAT),
        ("mTyreTreadTemp", _TYRE_FLOAT),
        ("mTyreLayerTemp", _TYRE_FLOAT),
        ("mTyreCarcassTemp", _TYRE_FLOAT),
        ("mTyreRimTemp", _TYRE_FLOAT),
        ("mTyreInternalAirTemp", _TYRE_FLOAT),
        # Car Damage
        ("mCrashState", c_uint),
        ("mAeroDamage", c_float),
        ("mEngineDamage", c_float),
        # Weather
        ("mAmbientTemperature", c_float),
        ("mTrackTemperature", c_float),
        ("mRainDensity", c_float),
        ("mWindSpeed", c_float),
        ("mWindDirectionX", c_float),
        ("mWindDirectionY", c_float),
        ("mCloudBrightness", c_float),
        # PCars2 additions (version 8)
        ("mSequenceNumber", c_uint),
        ("mWheelLocalPositionY", _TYRE_FLOAT),
        ("mSuspensionTravel", _TYRE_FLOAT),
        ("mSuspensionVelocity", _TYRE_FLOAT),
        ("mAirPressure", _TYRE_FLOAT),
        ("mEngineSpeed", c_float),
        ("mEngineTorque", c_float),
        ("mWings", c_float * 2),
        ("mHandBrake", c_float),
        # Additional race variables
        ("mCurrentSector1Times", c_float * _MAX_PART),
        ("mCurrentSector2Times", c_float * _MAX_PART),
        ("mCurrentSector3Times", c_float * _MAX_PART),
        ("mFastestSector1Times", c_float * _MAX_PART),
        ("mFastestSector2Times", c_float * _MAX_PART),
        ("mFastestSector3Times", c_float * _MAX_PART),
        ("mFastestLapTimes", c_float * _MAX_PART),
        ("mLastLapTimes", c_float * _MAX_PART),
        ("mLapsInvalidated", c_bool * _MAX_PART),
        ("mRaceStates", c_uint * _MAX_PART),
        ("mPitModes", c_uint * _MAX_PART),
        ("mOrientations", _VEC * _MAX_PART),
        ("mSpeeds", c_float * _MAX_PART),
        ("mCarNames", _STR * _MAX_PART),
        ("mCarClassNames", _STR * _MAX_PART),
        # Additional race variables
        ("mEnforcedPitStopLap", c_int),
        ("mTranslatedTrackLocation", _STR),
        ("mTranslatedTrackVariation", _STR),
        ("mBrakeBias", c_float),
        ("mTurboBoostPressure", c_float),
        ("mTyreCompound", (c_char * AMS2Constants.TYRE_COMPOUND_NAME_LENGTH_MAX) * AMS2Constants.TYRE_MAX),
        ("mPitSchedules", c_uint * _MAX_PART),
        ("mHighestFlagColours", c_uint * _MAX_PART),
        ("mHighestFlagReasons", c_uint * _MAX_PART),
        ("mNationalities", c_uint * _MAX_PART),
        ("mSnowDensity", c_float),
        # AMS2 additions (version 10+)
        # Session info
        ("mSessionDuration", c_float),
        ("mSessionAdditionalLaps", c_int),
        # Tyres
        ("mTyreTempLeft", _TYRE_FLOAT),
        ("mTyreTempCenter", _TYRE_FLOAT),
        ("mTyreTempRight", _TYRE_FLOAT),
        # DRS
        ("mDrsState", c_uint),
        # Suspension
        ("mRideHeight", _TYRE_FLOAT),
        # Input
        ("mJoyPad0", c_uint),
        ("mDPad", c_uint),
        ("mAntiLockSetting", c_int),
        ("mTractionControlSetting", c_int),
        # ERS
        ("mErsDeploymentMode", c_int),
        ("mErsAutoModeEnabled", c_bool),
        # Clutch State & Damage
        ("mClutchTemp", c_float),
        ("mClutchWear", c_float),
        ("mClutchOverheated", c_bool),
        ("mClutchSlipping", c_bool),
        ("mYellowFlagState", c_int),
        ("mSessionIsPrivate", c_bool),
        ("mLaunchStage", c_int),
    ]
