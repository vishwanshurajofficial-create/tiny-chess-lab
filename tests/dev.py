# Dev tests for engine.py: perft (legal move counts) + search benchmark +
# think() determinism. Run: python3 tests/dev.py
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as M


def perft_board(b, s, ep, ca, d):
    if d == 0:
        return 1
    total = 0
    for m in M.gen(b, s, ep, ca):
        nb, e2, c2 = M.make(b, s, ep, ca, m)
        total += perft_board(nb, 1 - s, e2, c2, d - 1)
    return total


def perft(fen, d):
    b, s, ep, ca = M.parse(fen)
    return perft_board(b, s, ep, ca, d)


CASES = [
    ("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1", [20, 400, 8902]),
    ("r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1", [48, 2039]),
    ("8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1", [14, 191, 2812]),
    ("r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1", [6, 264]),
    ("rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8", [44, 1486]),
    ("r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10", [46, 2079]),
]

fail = 0
for fen, expect in CASES:
    for d, want in enumerate(expect, 1):
        got = perft(fen, d)
        ok = got == want
        print(f"perft d{d} {'OK ' if ok else 'FAIL'} got={got} want={want}  {fen[:40]}")
        fail += 0 if ok else 1

# Benchmark: fixed 20000-node search from the Italian position.
b, s, ep, ca = M.parse("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
M.MAX_NODES = 20000
M.TT = {}
M.nodes = 0
M.killers = {}
M.history = {}
t0 = time.perf_counter()
try:
    M.search(6, -99999, 99999, b, s, ep, ca, 0, {}, ())
except M.Budget:
    pass
dt = time.perf_counter() - t0
n = M.nodes
print(f"search: {n} nodes in {dt:.2f}s -> {n/dt:.0f} nps")

# think() must be deterministic: same inputs -> same move, twice.
fen = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
legal = ["e1g1", "d2d4", "f3g5", "c3d5", "a2a3", "h2h3", "b2b3", "g2g3"]
m1 = M.think(fen, legal, "Alpha-beta, 500,000 nodes")
m2 = M.think(fen, legal, "Alpha-beta, 500,000 nodes")
ok = m1 == m2
print(f"think determinism {'OK' if ok else 'FAIL'}: {m1} vs {m2}")
print("budget_for checks:",
      M.budget_for("Alpha-beta, depth 2") == 10000,
      M.budget_for("Alpha-beta, 500,000 nodes") == 130000,
      M.budget_for("unknown thing") == 60000)

# think() must actually APPLY that budget, CONSUME it, and reset per-search
# state. A mapping that exists but is never wired up passes a budget_for()
# unit test, so this checks the real execution path end to end.
budget_ok = True
for name, want in (("Alpha-beta, depth 2", 10000),
                   ("Alpha-beta, depth 3", 20000),
                   ("Alpha-beta, depth 4", 35000),
                   ("Alpha-beta, 100,000 nodes", 60000),
                   ("Alpha-beta, 250,000 nodes", 90000),
                   ("Alpha-beta, 500,000 nodes", 130000),
                   ("Alpha-beta, 1,000,000 nodes", 150000),
                   ("Alpha-beta, 2,000,000 nodes", 150000),
                   ("totally unknown opponent", 60000)):
    M.history = {('X', 42): 999}   # poison: think() must clear it
    M.think(fen, legal, name)
    for why, bad in (
            (f"budget {M.MAX_NODES} != {want}", M.MAX_NODES != want),
            ("history was not reset", ('X', 42) in M.history),
            (f"only {M.nodes} of {want} nodes consumed", M.nodes != want),
            ("no move returned", not M.think(fen, legal, name))):
        if bad:
            budget_ok = False
            print(f"  FAIL think() for {name!r}: {why}")
    M.history = {('X', 42): 999}
print(f"think() applies budget, consumes it, resets history: "
      f"{'OK' if budget_ok else 'FAIL'}")
fail += 0 if budget_ok else 1
fail += 0 if ok else 1

sys.exit(1 if fail else 0)
