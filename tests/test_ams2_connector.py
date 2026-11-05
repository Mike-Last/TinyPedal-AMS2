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
from tinypedal.calculation import rotate_coordinate
from tinypedal.adapter.ams2_connector import SimAMS2
from tinypedal.adapter.ams2_data import (
    AMS2ParticipantInfo,
    AMS2SharedMemory,
    GameState,
    PitMode,
    RaceState,
    SessionState,
)
from tinypedal.adapter.ams2_sharedmemory import (
    AMS2Info,
    DamageTracker,
    ParticipantTracker,
    SessionCheck,
    spread_damage,
)

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


def set_world(vector, yaw: float, car_x: float, car_y: float) -> None:
    """Set world vector from vehicle frame (+x right, +y behind), inverse of the radar's rotation"""
    world_x, world_y = rotate_coordinate(3.14159265 - yaw, car_x, car_y)
    vector[0] = world_x
    vector[2] = -world_y  # lateral axis is -Z, as reader position_lateral


def damage_data(yaw: float = 0.7) -> AMS2SharedMemory:
    """Player at index 0 driving ahead at 50 m/s"""
    data = AMS2SharedMemory()
    set_participants(data, "Alice", "Bob")
    data.mOrientations[0][1] = -yaw  # as reader orientation_yaw
    set_world(data.mWorldVelocity, yaw, 0.0, -50.0)
    return data


def assert_direction(position, expected_x: float, expected_y: float) -> None:
    """Impact direction matches within rounding"""
    assert abs(position[0] - expected_x) < 1e-3 and abs(position[1] - expected_y) < 1e-3, position


def test_spread_damage():
    """Damage spreads over parts facing impact, capped per part, total kept"""
    # Front: front 50%, front corners 25% each
    parts = spread_damage((0.0,) * 8, 1.6, (0.0, -1.0))
    assert [round(part, 6) for part in parts] == [0.4, 0.8, 0.4, 0, 0, 0, 0, 0]
    # Right side
    parts = spread_damage((0.0,) * 8, 1.0, (1.0, 0.0))
    assert parts[4] > parts[2] > 0 and abs(parts[2] - parts[7]) < 1e-9 and parts[3] == 0
    # Unknown direction
    assert spread_damage((0.0,) * 8, 0.8, None) == (0.1,) * 8
    # Full parts spill over to the rest, never over max severity
    parts = spread_damage((0.0,) * 8, 10.0, (0.0, -1.0))
    assert max(parts) == 2.0 and abs(sum(parts) - 10.0) < 1e-9
    parts = spread_damage((2.0,) * 7 + (1.5,), 3.0, (0.0, -1.0))
    assert parts == (2.0,) * 8


def test_damage_tracker_wall_impact():
    """Sudden stop with damage is a front impact, damage goes to the front"""
    data = damage_data()
    tracker = DamageTracker()
    tracker.update(data, 0, 1.0)
    tracker.update(data, 0, 1.01)
    assert tracker.timestamp == 0

    # Hard braking alone (4 g at 100 Hz) does not count as an impact direction
    set_world(data.mWorldVelocity, 0.7, 0.0, -49.6)
    tracker.update(data, 0, 1.02)
    assert tracker._direction_strength == 0

    # Hit the wall ahead, damage registers a frame later
    set_world(data.mWorldVelocity, 0.7, 0.0, -20.0)
    tracker.update(data, 0, 1.03)
    data.mAeroDamage = 0.1
    tracker.update(data, 0, 1.04)
    assert tracker.timestamp == 1.04
    assert_direction(tracker.position, 0.0, -1.0)
    front_left, front, front_right, left, right, rear_left, rear, rear_right = tracker.severity
    assert front > front_left > 0 and abs(front_left - front_right) < 1e-6
    assert left == right == rear_left == rear == rear_right == 0
    assert abs(sum(tracker.severity) - 1.6) < 1e-6  # aero damage x 16

    # Pushed to the left by a hit on the right
    set_world(data.mWorldVelocity, 0.7, -8.0, -20.0)
    tracker.update(data, 0, 2.0)
    data.mAeroDamage = 0.2
    tracker.update(data, 0, 2.05)
    assert_direction(tracker.position, 1.0, 0.0)
    assert tracker.severity[4] > 0 and tracker.severity[3] == 0

    # Damage rise long after any velocity change has no direction, spreads evenly
    position = tracker.position
    before = tracker.severity
    data.mAeroDamage = 0.25
    tracker.update(data, 0, 5.0)
    assert tracker.timestamp == 5.0 and tracker.position == position
    assert all(abs(after - part - 0.1) < 1e-6 for part, after in zip(before, tracker.severity))

    # Repair scales all parts, keeping their share, and is not an impact
    before = tracker.severity
    data.mAeroDamage = 0.125
    tracker.update(data, 0, 6.0)
    assert all(abs(after - part * 0.5) < 1e-6 for part, after in zip(before, tracker.severity))
    assert tracker.timestamp == 5.0


def test_damage_tracker_collision():
    """Opponent collision gives direction of the opponent, over velocity change"""
    yaw = 2.0
    data = damage_data(yaw)
    tracker = DamageTracker()
    tracker.update(data, 0, 1.0)

    # Opponent hits the rear right while the car is pushed ahead
    set_world(data.mParticipantInfo[1].mWorldPosition, yaw, 1.0, 4.0)
    set_world(data.mWorldVelocity, yaw, 0.0, -55.0)
    data.mLastOpponentCollisionIndex = 1
    data.mLastOpponentCollisionMagnitude = 3.0
    tracker.update(data, 0, 2.0)
    assert tracker.timestamp == 2.0
    expected = 1 / 17 ** 0.5
    assert_direction(tracker.position, expected, 4 * expected)
    data.mAeroDamage = 0.05
    tracker.update(data, 0, 2.01)
    assert tracker.severity[6] > 0 and tracker.severity[7] > 0
    assert tracker.severity[0] == tracker.severity[1] == tracker.severity[2] == 0

    # Collision with an invalid index is ignored
    data.mLastOpponentCollisionIndex = -1
    tracker.update(data, 0, 3.0)
    assert tracker.timestamp == 2.01  # damage rise


def test_damage_tracker_resets():
    """Viewing another vehicle or a session reset starts from its current damage"""
    data = damage_data()
    tracker = DamageTracker()
    data.mAeroDamage = 0.5
    tracker.update(data, 0, 1.0)  # existing damage, not an impact
    assert tracker.timestamp == 0 and tracker.severity == (1.0,) * 8
    data.mAeroDamage = 0.25
    tracker.update(data, 1, 2.0)  # another vehicle with less damage
    assert tracker.timestamp == 0 and tracker.severity == (0.5,) * 8
    tracker.update(data, -1, 3.0)  # not synced, unchanged
    assert tracker.severity == (0.5,) * 8
    data.mLastOpponentCollisionIndex = 0
    data.mLastOpponentCollisionMagnitude = 1.0
    tracker.update(data, 1, 3.0)
    assert tracker.timestamp == 3.0
    tracker.reset()
    assert tracker.timestamp == 0 and tracker.position == (0.0, 0.0)
    data.mAeroDamage = 0.0
    tracker.update(data, 1, 0.5)
    assert tracker.severity == (0.0,) * 8


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

    # Impact from opponent collision, reported even with damage disabled
    damage = info._sync.damage
    data.mNumParticipants = 4
    data.mLastOpponentCollisionIndex = -1
    damage.update(data, 0, 5.0)
    assert vehicle.impact_time() == 0
    data.mLastOpponentCollisionIndex = 3
    data.mLastOpponentCollisionMagnitude = 2.5
    damage.update(data, 0, 10.0)
    assert vehicle.impact_time() == 10.0
    damage.update(data, 0, 20.0)
    assert vehicle.impact_time() == 10.0  # unchanged collision
    data.mLastOpponentCollisionMagnitude = 4.0
    damage.update(data, 0, 20.0)
    assert vehicle.impact_time() == 20.0
    assert vehicle.impact_position(1) == (0.0, 0.0)  # player only

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
