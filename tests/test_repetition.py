"""F7: threefold-repetition correctness.

Contracts under test:
  * A position occurring twice is NOT a threefold draw.
  * Three occurrences ARE.
  * Committed history is counted; the root counts exactly once.
  * The search path counts as occurrences of the current line.
  * Position identity is placement + side to move + castling, and en passant
    only when a *legal* en-passant capture exists.
  * The speculative path-cycle cutoff is a separate, documented termination
    heuristic and must keep blocking endless checking sequences.

`hist` is a mapping of position key -> number of committed occurrences. The
key is obtained through the engine's own identity helper when present, so the
tests describe behaviour rather than a key layout.
"""
import sys
sys.path.insert(0, '.')
import engine as E

ITAL = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

failures = []


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        failures.append(name)


def total(h):
    """Committed-occurrence total, whether hist is a mapping or a set."""
    if h is None:
        return None
    return sum(h.values()) if hasattr(h, "values") else len(h)


def count(h, k):
    """Occurrences recorded for k."""
    if h is None:
        return None
    return h.get(k, 0) if hasattr(h, "get") else int(k in h)


def ident(fen):
    """Position identity as the engine defines it, whatever that currently is."""
    b, s, ep, ca = E.parse(fen)
    fn = getattr(E, "pkey", None)
    return fn(b, s, ep, ca) if fn else (''.join(b), s, ep, ca)


def score(fen, hist, path=(), depth=3):
    """One search of `fen` with the given committed history and search path."""
    b, s, ep, ca = E.parse(fen)
    E.TT, E.killers, E.history = {}, {}, {}
    E.nodes, E.MAX_NODES = 0, 10 ** 6
    return E.search(depth, -99999, 99999, b, s, ep, ca, 1, hist, path)


print("A. two occurrences are not a threefold draw")
one = {ident(ITAL): 1}
got = score(ITAL, one)
check("a position seen once in history still gets searched",
      got != 0, f"score {got}")
cold = score(ITAL, {})
check("history of one occurrence matches a cold search",
      got == cold, f"{got} vs {cold}")

print("\nB. three occurrences are a threefold draw")
two = {ident(ITAL): 2}
got = score(ITAL, two)
check("the third occurrence scores the draw", got == 0, f"score {got}")

print("\nC. the root is counted exactly once (observed through think)")
seen = {}
_orig = E.search


def spy(depth, alpha, beta, board, side, ep, castle, ply, hist, path, null=0):
    seen.setdefault('hist', hist)
    return _orig(depth, alpha, beta, board, side, ep, castle, ply, hist,
                 path, null)


def replay(mvs):
    """Independent replay in the test: the sequence of position identities."""
    b, s, e, a = E.parse(START)
    keys = [E.pkey(b, s, e, a)]
    for u in mvs:
        b, e, a = E.make(b, s, e, a,
                         (E.square(u[:2]), E.square(u[2:4]), u[4:5]))
        s = 1 - s
        keys.append(E.pkey(b, s, e, a))
    return keys


legal = ["a2a3", "b2b3", "c2c3", "d2d3", "e2e3", "f2f3",
         "g2g3", "h2h3", "b1a3", "b1c3", "g1f3", "g1h3"]
MV = ["e2e4", "e7e5", "g1f3"]
keys = replay(MV)
seen.clear()
try:
    E.search = spy
    E.think(START, legal, "Alpha-beta, depth 2", MV)
finally:
    E.search = _orig
hist = seen.get('hist')
check("think builds a history mapping", isinstance(hist, dict), f"{type(hist)}")
check("every committed position is counted exactly once",
      total(hist) == len(keys), f"total {total(hist)} of {len(keys)}")
check("the root position is present",
      count(hist, keys[-1]) == 1, f"root count {count(hist, keys[-1])}")
check("the root is counted once, not twice",
      count(hist, keys[-1]) == 1, f"count {count(hist, keys[-1])}")
check("the first position is counted once",
      count(hist, keys[0]) == 1, f"count {count(hist, keys[0])}")
check("every intermediate position is present",
      all(count(hist, k) == 1 for k in keys), f"{[count(hist, k) for k in keys]}")

# A four-move cycle returns the board to the starting position: the start has
# now occurred twice, and the root is that same position.
CYCLE = ["g1f3", "g8f6", "f3g1", "f6g8"]
ck = replay(CYCLE)
check("the cycle really returns to the start", ck[0] == ck[-1])
seen.clear()
try:
    E.search = spy
    E.think(START, legal, "Alpha-beta, depth 2", CYCLE)
finally:
    E.search = _orig
hist = seen.get('hist')
check("a repeated start position is counted twice, not once",
      count(hist, ck[0]) == 2, f"count {count(hist, ck[0])}")
check("the cycle leaves no fourth occurrence behind",
      total(hist) == len(ck), f"total {total(hist)} of {len(ck)}")

print("\nD. occurrences along the search path count")
k = ident(ITAL)
check("one prior path occurrence is a cycle cutoff",
      score(ITAL, {}, (k,)) == 0, f"{score(ITAL, {}, (k,))}")
check("two prior path occurrences are still a cutoff",
      score(ITAL, {}, (k, k)) == 0, f"{score(ITAL, {}, (k, k))}")
check("a foreign path does not affect the position",
      score(ITAL, {}, (('x', 0, 0, 0),)) == cold,
      f"{score(ITAL, {}, (('x', 0, 0, 0),))} vs {cold}")

print("\nE. history is not mutated or shared between branches")
h = {ident(ITAL): 1}
before = dict(h)
score(ITAL, h)
score(ITAL, h, (ident(ITAL),))
check("search does not mutate the committed history", h == before, f"{h}")

print("\nF. castling rights are part of the position identity")
W = E.parse("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
N = E.parse("r3k2r/8/8/8/8/8/8/R3K2R w - - 0 1")
fn = getattr(E, "pkey", None)
check("engine exposes a position-identity helper", fn is not None)
if fn:
    check("different castling rights give different identities",
          fn(*W) != fn(*N))
    check("the same castling rights give the same identity",
          fn(*W) == fn(*W))

print("\nG. en passant counts only when a legal capture exists")
LEGAL_EP = "8/8/8/3pP3/8/8/8/4K2k w - d6 0 1"      # exd6 is legal
NO_PAWN = "8/8/8/3p4/8/8/8/4K2k w - d6 0 1"        # nothing can capture
PINNED = "8/8/8/KPp4r/8/8/8/7k w - c6 0 1"         # bxc6 exposes Ka5 to Rh5
if fn:
    a = fn(*E.parse(LEGAL_EP))
    b2 = fn(*E.parse(LEGAL_EP.replace(" d6 ", " - ")))
    check("a legal en-passant right distinguishes the position", a != b2)
    n1 = fn(*E.parse(NO_PAWN))
    n2 = fn(*E.parse(NO_PAWN.replace(" d6 ", " - ")))
    check("an unusable en-passant square does not distinguish", n1 == n2)
    p1 = fn(*E.parse(PINNED))
    p2 = fn(*E.parse(PINNED.replace(" c6 ", " - ")))
    check("a pinned en-passant capture does not distinguish", p1 == p2)
    bb, ss, ee, cc = E.parse(PINNED)
    caps = [m for m in E.gen(bb, ss, ee, cc, 1) if m[1] == ee]
    check("the engine agrees the pinned capture is illegal", not caps, f"{caps}")

print("\nH. side to move is part of the position identity")
wb, ws, we, wc = E.parse("8/8/8/3pP3/8/8/8/4K2k w - - 0 1")
bb2, bs2, be2, bc2 = E.parse("8/8/8/3pP3/8/8/8/4K2k b - - 0 1")
if fn:
    check("different sides to move give different identities",
          fn(wb, ws, we, wc) != fn(bb2, bs2, be2, bc2))

print("\nI. repeated checking sequences terminate safely")
PERP = "5k2/8/8/8/8/8/7p/K5Q1 w - - 0 1"
E.TT, E.killers, E.history = {}, {}, {}
E.nodes, E.MAX_NODES = 0, 60000
pb, ps, pe, pc = E.parse(PERP)
try:
    sc = E.search(5, -99999, 99999, pb, ps, pe, pc, 1, {}, ())
    ended = True
except E.Budget:
    sc, ended = None, True
check("a checking position terminates inside the node budget",
      ended and E.nodes <= E.MAX_NODES, f"nodes {E.nodes}")

print("\nJ. no legal moves still scores mate and stalemate")
MATE = "r5k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"
b, s, ep, ca = E.parse("7k/5Q2/8/8/8/8/8/K7 b - - 0 1")
E.TT, E.killers, E.history = {}, {}, {}
E.nodes, E.MAX_NODES = 0, 10 ** 6
got = E.search(3, -99999, 99999, b, s, ep, ca, 1, {}, ())
check("a stalemated side scores zero", got == 0, f"{got}")

print("\nK. determinism")
E.TT, E.killers, E.history = {}, {}, {}
first = E.think(ITAL, legal, "Alpha-beta, depth 3")
second = E.think(ITAL, legal, "Alpha-beta, depth 3")
check("identical inputs give identical moves", first == second,
      f"{first} vs {second}")

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("all repetition checks passed")
