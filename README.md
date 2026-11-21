# Tiny Chess Lab

An original, deterministic, compact chess engine in pure Python 3.13.
Standard library only, no network at runtime, no third-party packages,
no clocks in the engine — the search is bounded by a fixed node budget so
that every search replays byte for byte.

## Two-tier architecture

| Tier | Source | Artifact | Role |
|---|---|---|---|
| Reference | `engine.py` (20,321 B) | — | Full implementation: F1–F7 **and** F12 (halfmove clock, fifty-move claim and seventy-five-move rule). Source of truth and the target for future correctness work. |
| Compact frozen baseline | `archive/f7/engine.py` (17,941 B) | `main.py` (4,089 B) | The F7 milestone, preserved verbatim. **It does not contain F12** — F12 does not fit the cap (see `LIMITATIONS.md`). This is the exact source that produced the shipped artifact. |

`main.py` is *generated*, never hand-edited. `tools/build.py --tier compact`
strips docstrings and comments, packs the result with `makefun compress`, then
checks the byte cap, compiles it, compares its SHA-256 against the recorded
release hash, and rebuilds from scratch to confirm a byte-identical result. Any
failed check aborts and leaves `main.py` untouched; the artifact is written only
with an explicit `--install`.

Reproduction is a verified fact, not a claim:

```
archive/f7/engine.py  17,941 B  sha256 3042efc3…   (verbatim F7 source)
  -> strip            14,008 B  sha256 f97d4fc1…   (equals the packed payload)
  -> makefun compress  4,089 B  sha256 97a6b39f…   (byte-identical to main.py)
```

The two tiers are **not feature-equivalent**. Do not assume they are.

The two tiers are **not feature-equivalent**. Do not assume they are.

## Quick start

```bash
python3 -V                             # 3.13 target
for t in tests/dev.py tests/test_*.py; do python3 "$t" || echo "FAILED $t"; done
python3 tools/build.py --tier compact  # verify reproduction of main.py (no writes)
```

`--install` is required to actually write `main.py`:

```bash
python3 tools/build.py --tier compact --install   # rewrite main.py after all checks
python3 tools/build.py --tier reference           # expected to refuse (4,219 > 4,096)
```

Running the build needs the competition harness at `tiny-chess-01-kit/`
(see `RELEASE_MANIFEST.md` for the pinned archive hash). Running the tests does
not: `tests/test_build.py` skips its build checks when the kit is absent.

## Layout

```
engine.py               reference engine (development source of truth, has F12)
archive/f7/engine.py    frozen compact baseline (verbatim F7 source, no F12)
main.py                 shipped compact artifact (generated, sha256-pinned)
tools/build.py          reproducible strip -> pack -> verify -> rebuild -> install
tests/                  eleven suites, 502 assertions (see TESTING.md)
AGENTS.md               project engineering rules
ARCHITECTURE.md         how the engine works
TESTING.md              what is tested, how, and what is not
LIMITATIONS.md          known gaps, measured, with no wishful thinking
RELEASE_MANIFEST.md     exact bytes, hashes and reproduction steps
```

## Rules implemented

Complete legal chess movement — castling (with rights), en passant,
promotion, check, checkmate and stalemate — verified against published
perft reference counts on six standard positions, in both tiers.

Draw handling in the reference tier follows FIDE 9.3 (fifty-move **claim**,
from the position or by declaring a qualifying quiet move) and 9.6.2
(seventy-five moves, automatic, with checkmate taking precedence).
The compact tier implements neither; its host adjudicates those draws itself.

## No strength claims

No Elo, rating or playing-strength claim is made anywhere in this repository.
The material here is correctness evidence — perft, invariants, determinism —
not a strength measurement. Nothing in this project has been benchmarked
against a rated opponent under a real time control.
