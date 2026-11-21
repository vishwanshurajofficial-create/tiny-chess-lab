# F2 regression tests: quiescence search while the side to move is in check.
# Run: python3 tests/test_qsearch_check.py   (exit 0 = pass)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as E

failures = []


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        failures.append(name)


def reset(budget=10 ** 6):
    E.TT, E.killers, E.history = {}, {}, {}
    E.nodes, E.MAX_NODES = 0, budget


def qsearch(fen, alpha=-99999, beta=99999, ply=0):
    b, s, ep, ca = E.parse(fen)
    reset()
    return E.search(0, alpha, beta, b, s, ep, ca, ply, {}, ())


def in_check(fen):
    b, s = E.parse(fen)[:2]
    return bool(E.attacked(b, b.index('K' if s == 0 else 'k'), 1 - s))


def legal_moves(fen):
    b, s, ep, ca = E.parse(fen)
    return E.gen(b, s, ep, ca)


MATE = -(99000)          # mate score at ply 0
MATE_ISH = -90000        # anything this low is a forced loss


def evasion_max(fen, ply=0):
    """Independent oracle: in check, the value is the negamax of the legal
    evasions; with no evasions it is mate. Children are searched one ply
    deeper, exactly as the engine now does, so this is exact for a full
    window."""
    b, s, ep, ca = E.parse(fen)
    ms = E.gen(b, s, ep, ca)
    if not ms:
        return -(99000 - ply)
    best = -99999
    for m in ms:
        nb, e2, c2 = E.make(b, s, ep, ca, m)
        reset()
        v = -E.search(0, -99999, 99999, nb, 1 - s, e2, c2, ply + 1, {}, ())
        best = max(best, v)
    return best


def evasion_property(name, fen):
    """In check, quiescence must equal the best legal evasion (never stand-pat)."""
    got, want = qsearch(fen), evasion_max(fen)
    check(name, got == want, f"qsearch {got} vs evasion-max {want}")


# --------------------------------------------------------------------------
# 1. Checkmate must be recognized inside quiescence (no stand-pat escape).
# --------------------------------------------------------------------------
FOOLS = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 0 3"
BACKRANK = "R5k1/5ppp/8/8/8/8/8/6K1 b - - 0 1"
for name, fen in (("fool's mate", FOOLS), ("back-rank mate", BACKRANK)):
    check(f"{name}: no legal moves", legal_moves(fen) == [])
    check(f"{name}: in check", in_check(fen))
    check(f"{name}: qsearch scores mate", qsearch(fen) <= MATE_ISH,
          f"got {qsearch(fen)}")

# Mate at a deeper ply keeps its ply-relative score.
check("mate score tracks ply", qsearch(FOOLS, ply=6) == -(99000 - 6),
      f"got {qsearch(FOOLS, ply=6)}")

# --------------------------------------------------------------------------
# 2. Single check, quiet evasions only (zero captures available).
# --------------------------------------------------------------------------
QUIET = "4r2k/8/8/8/8/8/8/4K3 w - - 0 1"
check("quiet: in check", in_check(QUIET))
check("quiet: no capture evasions exist",
      E.gen(*E.parse(QUIET)[:4], 1) == [])
evasion_property("quiet evasion searched", QUIET)
stand = E.evaluate(E.parse(QUIET)[0])  # white to move, so stand-pat is this
check("quiet: stand-pat not returned", qsearch(QUIET) != stand,
      f"stand {stand} vs qsearch {qsearch(QUIET)}")

# --------------------------------------------------------------------------
# 3. Single check with a capture evasion.
# --------------------------------------------------------------------------
CAPTURE = "7k/8/8/8/8/8/4q3/4K3 w - - 0 1"
check("capture: in check", in_check(CAPTURE))
xe2 = [m for m in legal_moves(CAPTURE)
       if m[0] == E.square('e1') and m[1] == E.square('e2')]
check("capture evasion Kxe2 is legal", len(xe2) == 1, f"{xe2}")
evasion_property("capture evasion searched", CAPTURE)

# --------------------------------------------------------------------------
# 4. Double check: only king moves are legal.
# --------------------------------------------------------------------------
DOUBLE = "4r2k/8/8/8/1b6/8/8/4K3 w - - 0 1"
check("double: in check", in_check(DOUBLE))
king_only = all(m[0] == E.square('e1') for m in legal_moves(DOUBLE))
check("double: only king moves are legal", king_only,
      f"{[m for m in legal_moves(DOUBLE) if m[0] != E.square('e1')]}")
evasion_property("double check evasions searched", DOUBLE)

# --------------------------------------------------------------------------
# 5. Multiple legal evasions: best one wins, not the first.
# --------------------------------------------------------------------------
MULTI = "k3r3/8/8/8/8/8/8/3QK3 w - - 0 1"
check("multi: several evasions", len(legal_moves(MULTI)) > 2,
      f"{len(legal_moves(MULTI))} moves")
evasion_property("multiple evasions searched", MULTI)

# --------------------------------------------------------------------------
# 6. Every apparent evasion is illegal (pseudo-legal moves all refuted).
# --------------------------------------------------------------------------
b, s, ep, ca = E.parse(BACKRANK)
check("refuted: pseudo-legal pawn pushes exist but none is legal",
      legal_moves(BACKRANK) == [])
evasion_property("refuted evasions score mate", BACKRANK)

# --------------------------------------------------------------------------
# 7. Counter-check: an evasion that gives check back (recursion re-enters the
#    in-check branch). Must terminate and stay finite.
# --------------------------------------------------------------------------
COUNTER = "3k4/8/8/8/r3K3/8/8/3Q4 w - - 0 1"
check("counter: in check", in_check(COUNTER))
blocking_check = [m for m in legal_moves(COUNTER) if m[0] == E.square('d1')
                  and m[1] == E.square('d4')]
check("counter: Qd4 blocks and checks", len(blocking_check) == 1)
nb, e2, c2 = E.make(*E.parse(COUNTER)[:4], blocking_check[0])
check("counter: evading move gives check",
      E.attacked(nb, nb.index('k'), 0))  # attacked by white
evasion_property("counter-check evasion searched", COUNTER)
check("counter: score is finite", abs(qsearch(COUNTER)) < 90000,
      f"got {qsearch(COUNTER)}")

# --------------------------------------------------------------------------
# 8. Node-budget exhaustion during check evasion must abort safely.
# --------------------------------------------------------------------------
b, s, ep, ca = E.parse(QUIET)
before = list(b)
E.TT, E.killers, E.history = {}, {}, {}
E.nodes, E.MAX_NODES = 0, 1
raised = False
try:
    E.search(0, -99999, 99999, b, s, ep, ca, 0, {}, ())
except E.Budget:
    raised = True
check("budget: Budget raised during in-check qsearch", raised)
check("budget: board untouched by the abort", before == b)

# A slightly larger budget must not corrupt the result either.
E.nodes, E.MAX_NODES = 0, 60
try:
    E.search(0, -99999, 99999, b, s, ep, ca, 0, {}, ())
except E.Budget:
    pass
check("budget: board untouched after partial search", before == b)

# --------------------------------------------------------------------------
# 9. ply must advance exactly once per searched move, in quiescence too, so
#    mate distances are accurate at every recursive level.
# --------------------------------------------------------------------------
MATE_BY_CAPTURE = "r5k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"  # Rxa8# is a capture


def at_depth(depth, fen, ply):
    b, s, ep, ca = E.parse(fen)
    reset()
    return E.search(depth, -99999, 99999, b, s, ep, ca, ply, {}, ())


check("mate-by-capture is a capture move",
      any(m[0] == E.square('a1') and m[1] == E.square('a8')
          for m in E.gen(*E.parse(MATE_BY_CAPTURE)[:4], 1)))
check("qsearch mate-in-1 scores 98999, not 99000",
      at_depth(0, MATE_BY_CAPTURE, 0) == 98999,
      f"got {at_depth(0, MATE_BY_CAPTURE, 0)}")
check("qsearch mate distance tracks ply (ply 4 -> 98995)",
      at_depth(0, MATE_BY_CAPTURE, 4) == 98995,
      f"got {at_depth(0, MATE_BY_CAPTURE, 4)}")
check("qsearch agrees with the main search on mate distance",
      at_depth(0, MATE_BY_CAPTURE, 0) == at_depth(1, MATE_BY_CAPTURE, 0),
      f"qsearch {at_depth(0, MATE_BY_CAPTURE, 0)} vs search "
      f"{at_depth(1, MATE_BY_CAPTURE, 0)}")
check("qsearch never reports mate-in-0",
      at_depth(0, MATE_BY_CAPTURE, 0) < 99000)

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("all quiescence-in-check checks passed")
