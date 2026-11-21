# Architecture

## Position representation

A 120-square mailbox held in a flat list of 120 characters:

```
indices 0..20    padding ' '  (off-board sentinel)
indices 21..98   the 8x8 board, rank 8 first, with padding at each row edge
indices 99..119  padding ' '
```

Square `(rank, file)` maps to `21 + rank*10 + file`; `square('e2') = 85`.
Padding is `' '` and empty board squares are `'.'`, so a sliding piece loop can
walk until `board[t] != '.'` without any bounds check — the sentinel stops it.
`'.'` and `' '` are deliberately distinct, which is what lets a single test
`board[t] != '.'` distinguish "off board" from "empty".

In the reference tier the list carries one extra element, `board[CLOCK]` at
index 120, holding the halfmove clock (see F12 below). Everything else iterates
`range(21, 99)`, so the extra slot is invisible to move generation and
evaluation. `pkey` deliberately slices `b[:CLOCK]` so the clock never enters
repetition identity.

## Pieces

Uppercase is white, lowercase is black. `c.isupper()` therefore classifies a
whole side without a table. Promotions are written as
`(promo.upper(), promo)[side]`, which is why the same code handles both colours.

## Parsing

`parse(fen)` builds the mailbox from the placement field, converts the side to
`0/1`, the en-passant square to a mailbox index, and the castling field to four
bits (`KQkq` → 1, 2, 4, 8). It returns `(board, side, ep, castle)`; the compact
tier stops there, the reference tier appends the halfmove clock to the board.

## Move generation

`gen(board, side, ep, castle, captures_only=0)` emits `(from, to, promo)` triples.
Pseudo-legal generation is direct mailbox arithmetic (pawn offsets ±10/±9/±11,
knight deltas, king deltas, sliding rays). Legality is filtered at the end by
making each move and asking whether the mover's own king is attacked — simple,
obviously correct, and fast enough for the node budgets in use.

`attacked(board, sq, by)` checks knight and king deltas, pawn attack sources,
then four ray directions; the rook-vs-bishop distinction is `d % 9`, so the same
loop covers both.

## make()

`make()` is pure: it copies the board list, so it can never corrupt its input,
it handles castling rook transposition, en-passant victim removal, promotion
case, and clears castling bits when a king or corner rook moves or is captured.
In the reference tier it also advances or resets the halfmove clock — one site,
which is why no search call site can forget to thread it.

## Evaluation

Material plus five piece-square tables (P/N/B/R/Q) and separate middlegame and
endgame king tables, all stored as one 448-character string indexed by
`64*piece + square`; plus a bishop-pair term; plus a mop-up term that only
activates with a decisive margin in a near-bare endgame, pulling the winning
king in and driving the losing king to the edge.

Scores are returned from white's view and negated for black. Two invariants are
protected by tests: the black piece-square index is mirrored (`i ^= 56`, F1) and
the mop-up term uses the *losing* king for both colours (F13). Both exist
because the untested version was asymmetric.

## Search

Negamax alpha-beta with iterative deepening at the root:

- **Quiescence** at depth 0. In check the node resolves evasions instead of
  standing pat (F2) — standing pat while in check is a well-known blunder
  source. Recursion uses `ply + 1` (a fixed defect: it once reused `ply`).
- **Transposition table**, keyed by `(placement, side, ep, castle, clock)`.
  Flags are exact/lower/upper; mate scores are stored as a ply-free mate
  distance via `tt_store`/`tt_load`, and any score at or beyond ±90,000 is
  treated as a mate score (F4). Replacement is depth-preferred: a shallower
  search may not evict a deeper verdict (F6), and the slot is re-read before
  writing because a descendant may have transposed into it.
- **Null-move pruning** at R=2, skipped in check and in pawn-only endings.
- **Late move reductions** with a full-depth re-search when a reduced score
  beats alpha.
- **Check extension**, bounded by `EXT_PLY = 16` so a checking sequence cannot
  extend forever (F5).
- **Move ordering**: TT move, then MVV-LVA captures, then two killers per ply
  (newest first, F3), then history scores.

## Node budget, not a clock

`budget_for(opponent_name)` substring-matches the opponent description to a
fixed node cap (150k down to 10k, default 60k) and the search raises `Budget`
when the cap is hit. Because nothing depends on wall-clock time or on hash
randomisation, identical input produces identical output; this is asserted by
tests under three `PYTHONHASHSEED` values.

## F12 — halfmove clock (reference tier only)

The clock lives at `board[CLOCK]`, inside the position `make()` copies. A pawn
move or any capture resets it, anything else advances it — promotions and en
passant are pawn moves, so one test covers every reset event. Because it is
part of the position, sibling branches cannot contaminate each other.

Draw adjudication:

- **9.6.2, automatic**: past 149 halfmoves the game is drawn — unless the side
  to move has no legal move, in which case mate/stalemate handling runs and
  checkmate takes precedence.
- **9.3, claim**: a claim is available at or beyond 100 halfmoves, or at 99
  with a qualifying quiet move in hand. It is modelled as an extra
  zero-valued choice — a **floor** on the score, never a forced return — so a
  side may still prefer a continuation.

Repetition identity excludes the clock; transposition identity includes it, so
a score earned under one clock is never served for another.

## Why the compact tier is frozen

`main.py` is the LZMA-packed entrypoint, and its source is preserved verbatim at
`archive/f7/engine.py`. Packing changes the economics of refactoring: repeated
code costs almost nothing, so a change that removes duplication or introduces a
helper usually makes the artifact *larger* (measured: sharing the duplicated
quiescence sort key +10 bytes, flattening the piece-square table +0, removing
the `MAX_NODES` default +23). The compact tier therefore carries F1–F7 while the
reference tier additionally carries F12, which costs bytes the cap cannot
afford. See `LIMITATIONS.md` for the measured gap and `RELEASE_MANIFEST.md` for
reproduction.

The build is tier-explicit on purpose: `tools/build.py` requires
`--tier compact` or `--tier reference`, so the artifact can never be produced
from the wrong source by accident. The compact tier's output is pinned to a
recorded SHA-256, which is what turns "we think this source produced that
artifact" into a checkable statement — a one-character edit to the frozen
tier produces a 4,093-byte artifact that still fits the cap and is rejected by
the hash alone.
