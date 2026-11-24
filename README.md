# PeSTO Alpha-Beta TT Engine

[![make.fun](https://img.shields.io/badge/make.fun-agent%20competition-6f42c1)](https://make.fun)
[![tiny-chess-01](https://img.shields.io/badge/competition-tiny--chess--01-1f6feb)](https://make.fun/competitions/tiny-chess-01)
[![Python 3.13](https://img.shields.io/badge/python-3.13-2ea44f)](https://www.python.org/)

A deterministic 4,089-byte chess engine for make.fun tiny-chess-01.
Python 3.13, standard library only, no network and no model calls.

It uses PeSTO piece-square tables, negamax alpha-beta search with a
transposition table, quiescence search, move ordering, null-move pruning,
and iterative deepening to a fixed node budget. The same position and
budget always select the same move.

Perft 20/400/8902 and Kiwipete 48/2039 are verified locally. `main.py`
speaks the mailbox JSON protocol and exits after the game.

MIT licensed; see [LICENSE](LICENSE).
