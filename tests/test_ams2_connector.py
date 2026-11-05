"""
Test AMS2 sharedmemory API connector
"""

import ctypes
import inspect
import logging
import os
import re
import sys
from time import sleep

import pytest

sys.path.append(".")
sys.path.append("thirdparty")

from tinypedal.adapter import _reader, ams2_reader
from tinypedal.adapter.ams2_connector import SimAMS2
from tinypedal.adapter.ams2_data import (
    AMS2ParticipantInfo,
    AMS2SharedMemory,
    GameState,
    PitMode,
    RaceState,
    SessionState,
)
from tinypedal.adapter.ams2_sharedmemory import AMS2Info, ParticipantTracker, SessionCheck

# Game header, override with AMS2_SHARED_MEMORY_H environment variable
AMS2_HEADER = os.environ.get(
    "AMS2_SHARED_MEMORY_H",
    "C:/Program Files (x86)/Steam/steamapps/common/Automobilista 2/"
    "Support/SharedMemory/AMS2_SharedMemoryExampleApp/SharedMemory.h",
)
HEADER_TYPES = {
    "bool": ctypes.c_bool,
    "char": ctypes.c_char,
    "float": ctypes.c_float,
    "int": ctypes.c_int,
    "unsigned int": ctypes.c_uint,
    "ParticipantInfo": AMS2ParticipantInfo,
}


def test_struct():
    """Struct size must match AMS2 SharedMemory.h (version 14)"""
    assert ctypes.sizeof(AMS2SharedMemory) == 20700
    assert AMS2SharedMemory.mSequenceNumber.offset == 7320
    assert AMS2SharedMemory.mSessionDuration.offset == 20576
    assert AMS2SharedMemory.mLaunchStage.offset == 20696


def header_fields(header: str, struct_name: str) -> list:
    """Parse struct field (name, offset, size) list from SharedMemory.h"""
    header = re.sub(r"//[^\n]*", "", header)
    constants = {}
    for enum_body in re.findall(r"enum\s*\w*\s*\{(.*?)\}", header, re.S):
        value = -1
        for item in enum_body.split(","):
            name, _, assigned = item.partition("=")
            if not name.strip():
                continue
            try:
                value = int(assigned.strip(), 0) if assigned.strip() else value + 1
            except ValueError:  # expression, not used as array size
                continue
            constants[name.strip()] = value
    body = re.search(r"typedef struct\s*\{((?:(?!typedef struct).)*?)\}\s*" + struct_name + ";", header, re.S).group(1)
    fields = []
    for line in body.splitlines():
        code = line.split("//")[0].replace("volatile", "").strip()
        matched = re.fullmatch(r"(unsigned int|\w+)\s+(\w+)((?:\[\w+\])*);", code)
        if matched:
            ctype = HEADER_TYPES[matched.group(1)]
            for dim in reversed(re.findall(r"\[(\w+)\]", matched.group(3))):
                ctype = ctype * (int(dim) if dim.isdigit() else constants[dim])
            fields.append((matched.group(2), ctype))
    struct = type(struct_name, (ctypes.Structure,), {"_fields_": fields})
    return [(name, getattr(struct, name).offset, getattr(struct, name).size) for name, _ in fields]


@pytest.mark.skipif(not os.path.exists(AMS2_HEADER), reason="AMS2 SharedMemory.h not found")
def test_struct_matches_game_header():
    """Every field name, offset & size must match the installed game's SharedMemory.h"""
    with open(AMS2_HEADER, encoding="utf-8", errors="replace") as file:
        header = file.read()
    for struct, struct_name in (
        (AMS2ParticipantInfo, "ParticipantInfo"),
        (AMS2SharedMemory, "SharedMemory"),
    ):
        expected = header_fields(header, struct_name)
        assert expected, f"no fields parsed for {struct_name}"
        actual = [
            (name, getattr(struct, name).offset, getattr(struct, name).size)
            for name, *_ in struct._fields_
        ]
        assert actual == expected


def set_participants(data: AMS2SharedMemory, *names: str) -> None:
    """Set participant names"""
    data.mNumParticipants = len(names)
    for index, name in enumerate(names):
        data.mParticipantInfo[index].mName = name.encode()


def test_session_check():
    """Session resets are detected, viewing another vehicle is not a reset"""
    data = AMS2SharedMemory()
    data.mGameState = GameState.INGAME_PLAYING
    data.mSessionState = SessionState.RACE
    data.mParticipantInfo[0].mLapsCompleted = 5
    data.mParticipantInfo[1].mLapsCompleted = 3
    check = SessionCheck()
    assert check.is_reset(data, 0)  # first check
    assert not check.is_reset(data, 0)
    # View another vehicle with fewer laps, then back
    assert not check.is_reset(data, 1)
    assert not check.is_reset(data, 0)
    # Player lap count goes back
    data.mParticipantInfo[0].mLapsCompleted = 0
    assert check.is_reset(data, 0)
    # Session changed
    data.mSessionState = SessionState.QUALIFY
    assert check.is_reset(data, 0)
    assert not check.is_reset(data, 0)
    # Session restarted
    data.mGameState = GameState.INGAME_RESTARTING
    assert check.is_reset(data, 0)


def test_participant_tracker():
    """Grid position, lap start time, last lap valid state & pit stops"""
    data = AMS2SharedMemory()
    set_participants(data, "Alice", "Bob")
    tracker = ParticipantTracker()

    # Grid recorded before race start only
    data.mSessionState = SessionState.RACE
    data.mRaceState = RaceState.NOT_STARTED
    data.mParticipantInfo[0].mRacePosition = 2
    data.mParticipantInfo[1].mRacePosition = 1
    tracker.update(data, 0.0)
    data.mRaceState = RaceState.RACING
    data.mParticipantInfo[0].mRacePosition = 1
    data.mParticipantInfo[1].mRacePosition = 2
    tracker.update(data, 1.0)
    assert tracker.grid[:2] == [2, 1]

    # Lap start time & validity of the lap just completed
    data.mLapsInvalidated[1] = True
    tracker.update(data, 50.0)
    data.mParticipantInfo[0].mLapsCompleted = 1
    data.mParticipantInfo[1].mLapsCompleted = 1
    data.mLapsInvalidated[1] = False  # game clears flag on new lap
    tracker.update(data, 90.0)
    assert tracker.lap_start[:2] == [90.0, 90.0]
    assert tracker.last_valid[:2] == [True, False]

    # Pit stop counted once per stop
    data.mPitModes[0] = PitMode.DRIVING_INTO_PITS
    tracker.update(data, 100.0)
    data.mPitModes[0] = PitMode.IN_PIT
    tracker.update(data, 101.0)
    tracker.update(data, 102.0)
    data.mPitModes[0] = PitMode.DRIVING_OUT_OF_PITS
    tracker.update(data, 103.0)
    assert tracker.pitstops[:2] == [1, 0]
    data.mPitModes[0] = PitMode.IN_PIT
    tracker.update(data, 200.0)
    assert tracker.pitstops[:2] == [2, 0]

    tracker.reset()
    assert tracker.pitstops[:2] == [0, 0]
    assert tracker.grid[:2] == [0, 0]


def test_participant_tracker_follows_drivers():
    """Tracked data stays with drivers when participant indexes change"""
    data = AMS2SharedMemory()
    set_participants(data, "Alice", "Bob", "Carol")
    tracker = ParticipantTracker()
    tracker.update(data, 0.0)
    for index in range(3):
        data.mPitModes[index] = PitMode.IN_PIT
    tracker.update(data, 1.0)
    data.mPitModes[2] = PitMode.NONE
    tracker.update(data, 2.0)
    data.mPitModes[2] = PitMode.IN_PIT
    tracker.update(data, 3.0)
    assert tracker.pitstops[:3] == [1, 1, 2]  # Carol stopped twice
    for index in range(3):
        data.mPitModes[index] = PitMode.NONE

    # Alice & Carol swap indexes
    set_participants(data, "Carol", "Bob", "Alice")
    tracker.update(data, 4.0)
    assert tracker.pitstops[:3] == [2, 1, 1]

    # Bob leaves, Alice moves up, then Bob rejoins at the end
    set_participants(data, "Carol", "Alice")
    tracker.update(data, 5.0)
    assert tracker.pitstops[:2] == [2, 1]
    set_participants(data, "Carol", "Alice", "Bob")
    tracker.update(data, 6.0)
    assert tracker.pitstops[:3] == [2, 1, 1]

    # New driver takes an index, starts with no data
    set_participants(data, "Carol", "Alice", "Dave")
    tracker.update(data, 7.0)
    assert tracker.pitstops[:3] == [2, 1, 0]


def test_reader():
    """Every reader method returns without error while game not running"""
    api = SimAMS2()
    api.setup({
        "access_mode": 0,
        "memory_map_prefix": "",
        "character_encoding": "UTF-8",
        "enable_active_state_override": False,
        "active_state": True,
        "enable_player_index_override": False,
        "player_index": -1,
    })
    api.start()
    try:
        for group in api.reader():
            for name, _ in inspect.getmembers(type(group).__mro__[1], inspect.isfunction):
                getattr(group, name)()
    finally:
        api.stop()
    assert isinstance(group, _reader.Wheel)


def test_reader_values():
    """Reader converts AMS2 values (as observed from game) to TinyPedal units"""
    info = AMS2Info()
    data = AMS2SharedMemory()
    info._sync.player_data = data
    engine = ams2_reader.Engine(info)
    emotor = ams2_reader.ElectricMotor(info)
    vehicle = ams2_reader.Vehicle(info)
    wheel = ams2_reader.Wheel(info)

    # Turbo pressure, unset = -1
    data.mTurboBoostPressure = -1
    assert engine.turbo() == 0
    data.mTurboBoostPressure = 31767.4
    assert round(engine.turbo()) == 31767

    # Boost as electric motor
    assert emotor.state() == 0
    data.mBoostAmount = 40
    assert emotor.state() == 1
    assert abs(emotor.battery_charge() - 0.4) < 1e-6
    data.mBoostActive = True
    assert emotor.state() == 2

    # Impact from opponent collision
    info._sync.elapsed_time = 10.0
    data.mLastOpponentCollisionIndex = -1
    assert vehicle.impact_time() == 0
    data.mLastOpponentCollisionIndex = 3
    data.mLastOpponentCollisionMagnitude = 2.5
    assert vehicle.impact_time() == 10.0
    info._sync.elapsed_time = 20.0
    assert vehicle.impact_time() == 10.0  # unchanged collision
    data.mLastOpponentCollisionMagnitude = 4.0
    assert vehicle.impact_time() == 20.0

    # Snow counts as precipitation
    session = ams2_reader.Session(info)
    data.mRainDensity = 0.2
    data.mSnowDensity = 0.5
    assert session.raininess() == 0.5

    # Track limits surfaces count as off road
    data.mTerrain[:] = (0, 47, 49, 46)
    assert wheel.offroad() == 3


def test_api():
    """API test run"""
    # Add logger
    test_handler = logging.StreamHandler()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    logger.addHandler(test_handler)
    logger.info(__doc__)

    # Test run
    SEPARATOR = "=" * 50
    logger.info("Test API - Start")
    info = AMS2Info()
    info.setMode(1)  # set direct access
    info.setPlayerOverride(True)  # enable player override
    info.setPlayerIndex(0)  # set player index to 0
    info.start()
    sleep(0.2)

    logger.info(SEPARATOR)
    logger.info("Test API - Restart")
    info.stop()
    info.setMode()  # set copy access
    info.setPlayerOverride()  # disable player override
    info.start()

    logger.info(SEPARATOR)
    logger.info("Test API - Read")
    data = info.ams2Data
    version = data.mVersion
    driver = data.mParticipantInfo[info.playerIndex].mName
    track = data.mTrackLocation
    logger.info("version: %s", version if version else "not running")
    logger.info("driver : %s", driver if version else "not running")
    logger.info("track  : %s", track if version else "not running")

    logger.info(SEPARATOR)
    logger.info("Test API - Close")
    info.stop()


if __name__ == "__main__":
    test_struct()
    test_session_check()
    test_participant_tracker()
    test_participant_tracker_follows_drivers()
    test_reader()
    test_reader_values()
    test_api()
