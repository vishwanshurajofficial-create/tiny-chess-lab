# Testing

## Running

```bash
python3 tests/dev.py                      # perft regression
python3 tests/test_symmetry.py            # F1 / F13
python3 tests/test_qsearch_check.py       # F2
python3 tests/test_killers.py             # F3
python3 tests/test_extensions.py          # F5
python3 tests/test_tt_mates.py            # F4
python3 tests/test_tt_replacement.py      # F6
python3 tests/test_repetition.py          # F7
python3 tests/test_halfmove.py            # F12 (reference tier only)
python3 tests/test_standalone.py          # artifact gate: main.py, executed
python3 tests/test_build.py               # release gate: reproducible build
```

Every suite exits non-zero on failure and prints one `OK`/`FAIL` line per
assertion. Current totals: **11 suites, 502 assertions, 0 failures**.

`tests/gen_tables.py` and `tests/timed.py` are utilities, not suites:
the first regenerates the piece-square tables in `engine.py`, the second is a
timing harness for the node budget.

## What each suite protects

| Suite | Protects |
|---|---|
| `dev.py` | Perft counts, plus a regression that `think()` applies and consumes the opponent budget and resets its history each move |
| `test_symmetry.py` | Black piece-square mirror (F1); mop-up uses the losing king for both colours (F13) |
| `test_qsearch_check.py` | Quiescence resolves evasions while in check instead of standing pat; recursion advances `ply` (F2) |
| `test_killers.py` | At most two killers per ply, newest first, no unbounded growth (F3) |
| `test_extensions.py` | `EXT_PLY` bounds the check extension so a checking sequence terminates (F5) |
| `test_tt_mates.py` | Mate scores are stored as ply-free distances and re-anchor correctly at any ply, both signs (F4) |
| `test_tt_replacement.py` | A shallower search cannot evict a deeper verdict (F6) |
| `test_repetition.py` | Threefold needs three occurrences; committed counts and path counts; en passant only in the key when the capture is legal (F7) |
| `test_halfmove.py` | Clock parsing/reset/increment/branch isolation; FIDE 9.3 claim floor vs 9.6.2 automatic draw; mate precedence at 100/150/200; TT clock isolation (F12) |
| `test_standalone.py` | Executes `main.py` itself: size cap, compile, perft parity, evaluation parity, pinned move table, documented F12 gap, stdout cleanliness |
| `test_build.py` | Release gate: the frozen tier's size/hash, that it is the exact source inside the packed payload, that the build reproduces `main.py` byte-for-byte, that the reference tier refuses the cap, and that no stale candidate contradicts the artifact |

## External oracle used in the release audit

Move generation is verified against **published perft reference counts**
(Chess Programming Wiki), not against the project's own expectations:

| Position | Depths verified |
|---|---|
| Initial | 1–4 (20 / 400 / 8902 / 197281) |
| Kiwipete | 1–3 (48 / 2039 / 97862) |
| Position 3 (en passant, pins) | 1–4 (14 / 191 / 2812 / 43238) |
| Position 4 (promotions) | 1–3 (6 / 264 / 9467) |
| Position 5 | 1–3 (44 / 1486 / 62379) |
| Position 6 | 1–3 (46 / 2079 / 89890) |

All 20 counts match in **both** tiers. That covers castling, en passant,
promotion, pins, discovered checks and check evasion by construction.

## Release-audit property probes

Beyond the suites, the release audit ran 31 independent property checks with
hand-derived oracles: castling rights and rook transposition, en-passant victim
removal and rights, all four promotion pieces, checkmate/stalemate scoring,
evaluation mirror symmetry on six positions, quiescence vs stand-pat on an
in-check position, mate-distance invariance at ply 1/3/5, killer well-formedness,
termination under a 30-ply request, depth-preferred replacement, threefold
counts, state restoration, budget mapping and exact consumption, and
determinism. **0 engine findings; 3 defects were in the audit probe itself and
were fixed there, not in the engine** (a probe that compared raw mate scores
across plies instead of mate distances, a probe that misread `hist` as total
rather than prior occurrences, and a tautological reset assertion).

## Determinism

Searches are bounded by node count, never by time, and the engine does not
depend on hash ordering: repeated runs and `PYTHONHASHSEED=1/7/2024` produce
identical moves in both tiers.

## Build reproducibility

Reproduction is checked, not asserted. `tools/build.py --tier compact` runs the
pipeline and requires four independent conditions to hold: byte count ≤ 4,096,
`py_compile` success, candidate SHA-256 equal to the recorded release hash, and
a byte-identical result from a second from-scratch build. `--install` is
required to write `main.py`, so a failing build cannot damage the artifact.

Both the size gate and the hash gate were mutation-tested:

| Mutation | Observed | Result |
|---|---|---|
| Wrong expected hash | candidate correct | rejected: pin mismatch |
| One character changed in the frozen tier (`EXT_PLY 16→17`) | artifact grew to 4,093 B — still **within** the cap | rejected by the hash alone |
| Development source (`F12`) | 4,219 B | rejected: over budget by 123 |

In every mutation case `main.py` was left bit-for-bit untouched. The second row
is the important one: a cap check alone would have accepted a corrupted
artifact, which is why the release hash is part of the build rather than a note
in a document.

## Not tested

- No playing-strength measurement of any kind: no Elo, no games against rated
  engines, no opening-book or endgame-tablebase comparison.
- No real time-control testing. Node caps were timed on one host only
  (130k nodes ≈ 6.3 s), and that timing is not a commitment.
- No independent move-generation oracle beyond perft.
- No fuzzing of FEN parsing against malformed input.
- Killer and replacement policies were compared on small corpora, not at scale.
- `main.py` is only tested for the behaviour it implements — the F12 checks in
  `test_halfmove.py` cannot run against it and are not silently skipped; the
  gap is asserted explicitly in `test_standalone.py`.
- Build reproduction is only exercised when the vendor kit is present; without
  it `test_build.py` reports `SKIP` rather than passing silently.
