# Limitations

Everything below is measured or verified, not estimated. Where a number appears,
it was produced by running the code in this repository.

## 1. The shipped artifact does not contain F12 (halfmove clock)

`main.py` is built from the frozen F7 baseline preserved at
`archive/f7/engine.py`. The corrected F12 implementation in `engine.py` does not
fit the 4,096-byte cap:

| Candidate | Bytes | vs cap |
|---|---|---|
| `main.py` as shipped (F7) | **4,089** | −7 |
| F12 with FIDE claim model | 4,219 | **+123** |
| F12 with host-style automatic draw only | 4,156 | +60 |
| host-style, minus diagnostics | 4,139 | +43 |
| host-style, minus diagnostics and initialisers | 4,133 | +37 |

Even deleting every diagnostic and initialiser leaves the artifact 37 bytes
over. Every competing byte-saving idea was measured and rejected as neutral or
negative: sharing the duplicated quiescence sort key **+10**, flattening the
piece-square table to a single literal **+0**, removing the `MAX_NODES` default
**+23**, shortening the budget needles **+11**. The packer's compression
already reduces repeated code to near zero, so "remove duplication" is not a
lever here.

**Measured consequence.** In a won ending with the halfmove clock at 99, the
shipped tier cannot distinguish a clock-resetting move from a quiet one:

| move at clock 99 | kind | shipped | reference |
|---|---|---|---|
| `e2e3` | resets clock | +60 | +60 |
| `e1f2` / `e1d2` | quiet → clock 100 | **+60** | **0** |
| `e1f1` / `e1d1` | quiet → clock 100 | +40 | 0 |

The shipped engine plays a quiet move and converts a win into a draw. This is
a real strength defect, not a cosmetic one, and it is unfixable within the cap.

## 2. No dead-position (insufficient material) detection

Neither tier implements FIDE 5.2.2, so both misprice positions that are already
drawn:

| Position | FIDE | `evaluate()` | search d3 |
|---|---|---|---|
| K v K | dead | −70 | −40 |
| K+B v K | dead | **+250** | **+300** |
| K+N v K | dead | +220 | +295 |
| K+B v K+B, same colour | dead | −75 | −30 |
| K+N+N v K | alive | +500 | +595 |
| K+P v K | alive, winnable | +10 | +60 |

The engine therefore values a dead draw (+300) above a winnable pawn ending
(+60) and can steer into drawn material. A minimal correct check (no pawns,
rooks or queens; fewer than two minor pieces, or all bishops on one colour)
was measured at **103 bytes** of packed size, which would put the artifact 226
bytes over the cap. It is not implemented in either tier.

## 3. No draw-claim channel in the protocol

The engine's only outputs are moves: the client speaks `/game` and `/move`, and
there is no verb to claim a draw. The host arbiter adjudicates automatically —
checkmate, then stalemate, then dead position, then threefold, then
`halfmove >= 100` — and it runs after *every* move, so a position with a
claimable clock is never delivered to the engine.

The reference tier's 9.3 claim model is therefore **unexercisable in play**. It
is retained because it is the correct general model and because it is what
makes the 99/100 boundary safe: any quiet move at clock 99 hands the opponent a
claimable position, so every quiet move scores ≤ 0, which is exactly the host's
verdict. The residual divergence — a search node at clock ≥ 100 being treated
as playable when the host would already have ended the game — is unreachable
and, by that sign argument, cannot change a delivered move.

## 4. Evaluation is untuned, and no strength is claimed

Material values and piece-square tables are conventional starting points. There
is no tapered evaluation (F10 was never implemented): the king table switches
between two fixed tables at a phase threshold rather than interpolating.

**No Elo, rating or playing-strength claim is made.** Nothing in this repository
has been measured against a rated opponent, and no games have been played under
a real time control.

## 5. Budget is nodes, not time

Search is capped by node count so that results are reproducible. Node counts do
not translate into wall-clock guarantees: 130k nodes took ≈6.3 s on the
development host, and a slower host with a per-move time limit could overrun.
Budgets were set from measurements on one machine and have not been
recalibrated.

## 6. Representation and structure limits

- The position list is heterogeneous in the reference tier: indices 21–98 are
  characters, index 120 is an integer. Any future `''.join(board)` breaks, and
  `pkey` must keep slicing `b[:CLOCK]`.
- The transposition table is an unbounded dict with no aging or eviction, and
  depth-preferred replacement is only safe while the table is unbounded.
- Including the clock in the transposition key costs hit rate: 47.6% → 42.9%
  measured, about −0.8% nodes/second.
- The compact tier's per-game diagnostic prints an unreadable dictionary dump
  rather than a readable one-line result; the readable form was given up for
  bytes during F7 and has never been restored.
- Killers and history are reset every move, so ordering knowledge does not
  persist across a game.

## 7. Test coverage limits

See `TESTING.md` § "Not tested". In short: perft and invariants are well
covered; strength, time controls and malformed input are not covered at all.
