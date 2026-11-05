# Unofficial TinyPedal fork: Automobilista 2

**This is an unofficial, personal fork** of [TinyPedal/TinyPedal](https://github.com/TinyPedal/TinyPedal).
It is not made, endorsed or supported by the TinyPedal developers, so please do not take problems with it to them.

I made it to get Automobilista 2 support and a few features I want on my own rig. The fork's
changes were **written with AI (Claude, by Anthropic)** at my direction, and tested by me on my own
setup only. It is shared as-is, in case it is useful to someone else.

## License

TinyPedal is licensed under the GNU GPL version 3 or later, and so is this fork: see [LICENSE.txt](./LICENSE.txt).
The TinyPedal icon and the files in `images` stay under CC BY-SA 4.0, and third-party notices are in
`docs/licenses`. As GPLv3 section 5 asks, this file records what the fork modified; the changes date from 2026
and every change is in this repository's git history, on top of the upstream release tags it merges.

## What the fork changes

The fork adds:

- **Automobilista 2 API** (`tinypedal/adapter/ams2_*.py`): reads AMS2's built-in shared memory. In game,
  set `Options -> System -> Shared Memory` to `Project CARS 2`, then pick `API -> Automobilista 2`.
- **Watchlist widget** (`tinypedal/widget/watchlist.py`): a Relative widget that only shows the drivers
  named in its `watched_driver_names` option (friends or other notable drivers) plus the player, with every
  Relative option. It subclasses the Relative widget through a small `relative_list()` hook in `relative.py`,
  and its defaults are copied from Relative's, so new upstream Relative options carry over.
- **Build fix**: `Qt5Qml.dll` is bundled by `freeze_py2exe.py`, without it the py2exe build fails at startup.

See the README and `docs/customization.md` for what the AMS2 API supports and what the game does not provide.

## Releases

`.github/workflows/upstream-sync.yml` checks upstream every 6 hours. When upstream publishes a new release
it merges the release tag into `main`, runs the fork's tests, builds the exe with py2exe (Python 3.10,
PySide2 5.15), checks that the exe starts, and publishes a release here tagged `ams2-<version>-<run>` with
`TinyPedal-ams2-<version>.zip` attached. Merged upstream tags are marked `upstream-merged/<tag>`.
A merge conflict or a failed build opens an issue and leaves `main` untouched. A manual run of the workflow
builds `main` and publishes a release.

Before building, `.github/scripts/check_upstream_licence.py` checks whether the upstream release changes
licence terms: `LICENSE.txt`, `images/CC-BY-SA-4.0.txt`, `docs/licenses/`, the README `License` section
(ignoring copyright years), licence lines in Python file headers, and licence files of moved `thirdparty`
submodules. It only looks at what upstream changed, not at the fork's own edits. If anything changed, the
release is not merged, built or released, and an issue shows the changes. Upstream adds a library licence
a few times a year, which also stops the sync for review. To accept a release after reviewing it, merge it
by hand, push, and tag the merge `upstream-merged/<tag>`.

## Install

SimRig Manager installs and updates it (`tinypedalFork` block, `Update-TinyPedalFork.ps1` pre-launch) into
`%LOCALAPPDATA%\Programs\TinyPedal-ams2`. That folder is **deleted and replaced on every update**, so keep
user data elsewhere: in TinyPedal's `config.json` (`%APPDATA%\TinyPedal`), point every `user_path` entry at
a folder outside the install folder, e.g. `Documents\TinyPedal\settings\`.

## Build locally

```
uv venv --python 3.10 .venv
uv pip install --python .venv PySide2==5.15.2.1 psutil==6.1.1 py2exe==0.14.2.0
git submodule update --init
.venv/Scripts/python freeze_py2exe.py -c
```

The build lands in `dist\TinyPedal` and `-c` wipes that folder first, so do not run TinyPedal from it.

## Tests

```
uv pip install --python .venv pytest
.venv/Scripts/python -m pytest tests/test_ams2_connector.py tests/test_watchlist.py
```

`test_ams2_connector.py` covers the AMS2 data structure, unit conversions, session reset detection, and the
pit stop, grid and lap validity tracking that TinyPedal does itself, and the impact direction and damage
location it estimates. With AMS2 installed in the default Steam
folder it also checks every field against the game's own `Support/SharedMemory/.../SharedMemory.h` (set
`AMS2_SHARED_MEMORY_H` to use another path), otherwise that test is skipped. `test_watchlist.py` covers the
Watchlist name matching and row selection.
