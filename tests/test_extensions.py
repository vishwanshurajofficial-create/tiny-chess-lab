# F5 regression tests: check extensions must be bounded, and the bound must
# stay inert on ordinary positions.
# Run: python3 tests/test_extensions.py   (exit 0 = pass)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as E

failures = []


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        failures.append(name)


def alg(sq):
    r, f = divmod(sq - 21, 10)
    return "abcdefgh"[f] + str(8 - r)


def uci(m):
    return None if m is None else alg(m[0]) + alg(m[1]) + (m[2] or "")


DEFAULT_CAP = getattr(E, 'EXT_PLY', None)


def run(fen, depth, limit, budget=400000):
    """Fixed-depth search from ply 1. Reports peak MAIN-search ply reached."""
    E.EXT_PLY = limit
    peak = [0]
    orig = E.search

    def wrapper(*a, **kw):
        if a[0] >= 1 and a[7] > peak[0]:
            peak[0] = a[7]
        return orig(*a, **kw)

    E.search = wrapper
    b, s, ep, ca = E.parse(fen)
    E.TT, E.killers, E.history = {}, {}, {}
    E.nodes, E.MAX_NODES = 0, budget
    score, best = None, None
    try:
        alpha, cur = -99999, None
        for m in E.gen(b, s, ep, ca):
            nb, e2, c2 = E.make(b, s, ep, ca, m)
            sc = -E.search(depth - 1, -99999, -alpha, nb, 1 - s, e2, c2, 1,
                           {}, ())
            if cur is None or sc > alpha:
                alpha, cur = sc, m
        score, best = alpha, cur
    except E.Budget:
        pass
    finally:
        E.search = orig
    return dict(score=score, move=uci(best), nodes=E.nodes, peak=peak[0])


def run_guarded(*args, **kw):
    try:
        return run(*args, **kw)
    finally:
        E.EXT_PLY = DEFAULT_CAP


ITALIAN = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
KIWI = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"
ENDGAME = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1"
CHECK_RICH = "8/8/8/2k5/8/8/4Q3/2K5 w - - 0 1"
PERPETUAL = "5k2/8/8/8/8/8/7p/K5Q1 w - - 0 1"
TWO_QUEENS = "5k2/8/8/8/8/8/4q3/K5Q1 w - - 0 1"
MATE_IN_1 = "6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"
MATE_IN_2 = "6k1/5ppp/8/8/8/8/1Q6/6K1 w - - 0 1"
CHECKED = "4r2k/8/8/8/8/8/8/4K3 w - - 0 1"

# --------------------------------------------------------------------------
# 1. The bound exists and is sane.
# --------------------------------------------------------------------------
check("engine defines EXT_PLY", DEFAULT_CAP is not None, f"{DEFAULT_CAP}")
check("EXT_PLY is a positive int below 64",
      isinstance(DEFAULT_CAP, int) and 0 < DEFAULT_CAP < 64, f"{DEFAULT_CAP}")

# --------------------------------------------------------------------------
# 2. The cap is inert on ordinary positions: identical score, move and node
#    count to an effectively unlimited search.
# --------------------------------------------------------------------------
for name, fen, depth in (("italian", ITALIAN, 4), ("kiwipete", KIWI, 4),
                         ("endgame", ENDGAME, 5)):
    free = run_guarded(fen, depth, 10 ** 6)
    capped = run_guarded(fen, depth, DEFAULT_CAP)
    check(f"{name}: cap inert (score)", free['score'] == capped['score'],
          f"{free['score']} vs {capped['score']}")
    check(f"{name}: cap inert (move)", free['move'] == capped['move'],
          f"{free['move']} vs {capped['move']}")
    check(f"{name}: cap inert (nodes)", free['nodes'] == capped['nodes'],
          f"{free['nodes']} vs {capped['nodes']}")

# --------------------------------------------------------------------------
# 3. The default cap never binds on any benchmark position at a real budget:
#    this pins the documented finding that extensions are already bounded.
# --------------------------------------------------------------------------
for name, fen in (("check-rich", CHECK_RICH), ("perpetual", PERPETUAL),
                  ("two-queens", TWO_QUEENS)):
    free = run_guarded(fen, 6, 10 ** 6)
    capped = run_guarded(fen, 6, DEFAULT_CAP)
    check(f"{name}: default cap inert", free['score'] == capped['score']
          and free['nodes'] == capped['nodes'],
          f"{free['score']}/{free['nodes']} vs {capped['score']}/{capped['nodes']}")

# --------------------------------------------------------------------------
# 4. Structural bound: past the cap, ply may advance only while depth falls,
#    so peak main ply <= EXT_PLY + depth. Tested with a deliberately tight cap.
# --------------------------------------------------------------------------
for depth in (3, 5):
    r = run_guarded(CHECK_RICH, depth, 2)
    check(f"tight cap bounds max ply at depth {depth}",
          r['peak'] <= 2 + depth, f"peak {r['peak']}")

# --------------------------------------------------------------------------
# 5. A tight cap really does bind, and clipping extensions costs depth:
#    evidence that the extension is load-bearing, not decorative.
# --------------------------------------------------------------------------
free = run_guarded(CHECK_RICH, 6, 10 ** 6)
tight = run_guarded(CHECK_RICH, 6, 2)
check("tight cap reduces work", tight['nodes'] < free['nodes'],
      f"{tight['nodes']} vs {free['nodes']}")

# --------------------------------------------------------------------------
# 6. Check-rich positions terminate with a finite, non-mate score.
# --------------------------------------------------------------------------
for name, fen in (("perpetual", PERPETUAL), ("check-rich", CHECK_RICH),
                  ("two-queens", TWO_QUEENS)):
    r = run_guarded(fen, 6, DEFAULT_CAP, budget=150000)
    check(f"{name}: terminates finite",
          r['score'] is not None and abs(r['score']) < 90000,
          f"score {r['score']}")

# --------------------------------------------------------------------------
# 7. Checkmate detection and mate distance preserved.
# --------------------------------------------------------------------------
m1 = run_guarded(MATE_IN_1, 2, DEFAULT_CAP)
m2 = run_guarded(MATE_IN_2, 3, DEFAULT_CAP)
check("mate in 1 still 98999", m1['score'] == 98999, f"{m1['score']} {m1['move']}")
check("mate in 2 still found", m2['score'] is not None and m2['score'] >= 98998,
      f"{m2['score']} {m2['move']}")

# --------------------------------------------------------------------------
# 8. Check evasion preserved.
# --------------------------------------------------------------------------
r = run_guarded(CHECKED, 3, DEFAULT_CAP)
legal = [uci(m) for m in E.gen(*E.parse(CHECKED)[:4])]
check("single check returns a legal evasion", r['move'] in legal,
      f"{r['move']} in {legal}")

# --------------------------------------------------------------------------
# 9. Budget abort must not corrupt the board.
# --------------------------------------------------------------------------
b, s, ep, ca = E.parse(CHECK_RICH)
before = list(b)
E.TT, E.killers, E.history = {}, {}, {}
E.nodes, E.MAX_NODES = 0, 1
raised = False
try:
    E.search(6, -99999, 99999, b, s, ep, ca, 0, {}, ())
except E.Budget:
    raised = True
check("budget abort raises and leaves the board intact", raised and before == b)

# --------------------------------------------------------------------------
# 10. Repeated identical searches are identical.
# --------------------------------------------------------------------------
first = run_guarded(CHECK_RICH, 5, DEFAULT_CAP)
second = run_guarded(CHECK_RICH, 5, DEFAULT_CAP)
check("repeated searches identical",
      (first['score'], first['move'], first['nodes'], first['peak']) ==
      (second['score'], second['move'], second['nodes'], second['peak']),
      f"{first} vs {second}")

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("all check-extension checks passed")
