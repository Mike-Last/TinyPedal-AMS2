"""
Test AMS2 sharedmemory API connector
"""

import ctypes
import inspect
import logging
import sys
from time import sleep

sys.path.append(".")
sys.path.append("thirdparty")

from tinypedal.adapter import _reader
from tinypedal.adapter.ams2_connector import SimAMS2
from tinypedal.adapter.ams2_data import AMS2SharedMemory
from tinypedal.adapter.ams2_sharedmemory import AMS2Info


def test_struct():
    """Struct size must match AMS2 SharedMemory.h (version 14)"""
    assert ctypes.sizeof(AMS2SharedMemory) == 20700
    assert AMS2SharedMemory.mSequenceNumber.offset == 7320
    assert AMS2SharedMemory.mSessionDuration.offset == 20576
    assert AMS2SharedMemory.mLaunchStage.offset == 20696


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
    test_reader()
    test_api()
