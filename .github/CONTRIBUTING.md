# Contributing to this unofficial TinyPedal fork

> [!WARNING]
> This is an **unofficial fork** of [TinyPedal](https://github.com/TinyPedal/TinyPedal). It is not made, endorsed or supported by the TinyPedal developers. It adds Automobilista 2 support and a few features I want, and the fork's code was **written with AI (Claude)** at my direction.

This guide is for this fork only. For official TinyPedal, follow TinyPedal's own [contributing guide](https://github.com/TinyPedal/TinyPedal/blob/master/CONTRIBUTING.md) (it is also in this repository as [CONTRIBUTING.md](../CONTRIBUTING.md), kept unchanged from upstream).

## Reporting issues

Report problems with this fork in [this repository's issues](https://github.com/Mike-Last/TinyPedal-AMS2/issues), **not** in TinyPedal's.

If a problem also happens with official TinyPedal (from [TinyPedal's releases](https://github.com/TinyPedal/TinyPedal/releases), without this fork), it is an upstream problem: report it to TinyPedal, following their guide.

When reporting, please include the fork release you use (for example `ams2-2.52.0-14`), the game and session type, and what you expected to happen.

## Pull requests

Pull requests for this fork go to [this repository](https://github.com/Mike-Last/TinyPedal-AMS2/pulls). This is a personal fork, so changes are only taken if they fit what I use it for.

- Keep changes to upstream files small, so that merging new TinyPedal releases stays easy. New code goes in new files where possible, as the AMS2 adapter (`tinypedal/adapter/ams2_*.py`) and Watchlist widget (`tinypedal/widget/watchlist.py`) do.
- Follow TinyPedal's code style, and keep game API access read-only.
- Run the fork's tests, see [FORK-AMS2.md](../FORK-AMS2.md#tests).

## Nothing from this fork goes to TinyPedal

TinyPedal does not accept AI-generated code. Since this fork's code was written with AI, **do not submit any of it to TinyPedal**, in pull requests or otherwise.
