# TinyPedal fork: Automobilista 2

This is a private fork of [TinyPedal/TinyPedal](https://github.com/TinyPedal/TinyPedal) that adds:

- **Automobilista 2 API** (`tinypedal/adapter/ams2_*.py`): reads AMS2's built-in shared memory. In game,
  set `Options -> System -> Shared Memory` to `Project CARS 2`, then pick `API -> Automobilista 2`.
- **Friends widget** (`tinypedal/widget/friends.py`): position, last and best lap of the drivers named in
  its `friend_names` option. Shows a placeholder row while no friend is in the session, so the window stays
  capturable by OpenKneeboard.
- **Build fix**: `Qt5Qml.dll` is bundled by `freeze_py2exe.py`, without it the py2exe build fails at startup.

See the README and `docs/customization.md` for what the AMS2 API supports and what the game does not provide.

## Releases

`.github/workflows/upstream-sync.yml` checks upstream every 6 hours. When upstream publishes a new release
it merges the release tag into `main`, runs the AMS2 tests, builds the exe with py2exe (Python 3.10,
PySide2 5.15), checks that the exe starts, and publishes a release here tagged `ams2-<version>-<run>` with
`TinyPedal-ams2-<version>.zip` attached. Merged upstream tags are marked `upstream-merged/<tag>`.
A merge conflict or a failed build opens an issue and leaves `main` untouched. A manual run of the workflow
builds `main` and publishes a release.

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
