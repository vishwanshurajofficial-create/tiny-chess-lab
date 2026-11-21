# F3 regression tests: killer-move storage must be bounded and ordered.
# Run: python3 tests/test_killers.py   (exit 0 = pass)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as E

failures = []


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        failures.append(name)


START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
ITALIAN = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
KIWI = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1"

sq = E.square
M1 = (sq('b1'), sq('a3'), '')
M2 = (sq('b1'), sq('c3'), '')
M3 = (sq('g1'), sq('f3'), '')


def search_once(fen, depth, budget=40000, alpha=-99999, beta=99999):
    b, s, ep, ca = E.parse(fen)
    E.TT, E.killers, E.history = {}, {}, {}
    E.nodes, E.MAX_NODES = 0, budget
    try:
        E.search(depth, alpha, beta, b, s, ep, ca, 0, {}, ())
    except E.Budget:
        pass
    return E.killers


# --------------------------------------------------------------------------
# 1. Bounded storage: never more than two entries per ply, no duplicates.
# --------------------------------------------------------------------------
for fen, depth, budget in ((ITALIAN, 6, 60000), (KIWI, 5, 60000),
                           (START, 5, 40000)):
    k = search_once(fen, depth, budget)
    worst = max((len(v) for v in k.values()), default=0)
    total = sum(len(v) for v in k.values())
    dupes = sum(len(v) - len(set(v)) for v in k.values())
    check(f"max 2 entries per ply [{fen[:12]}]", worst <= 2,
          f"worst {worst} over {len(k)} plies")
    check(f"no duplicate killers [{fen[:12]}]", dupes == 0, f"{dupes} duplicates")
    check(f"total bounded to 2*plies [{fen[:12]}]", total <= 2 * len(k),
          f"{total} entries, {len(k)} plies")

# --------------------------------------------------------------------------
# 2. Newest killer receives priority; both killers outrank ordinary quiets.
# --------------------------------------------------------------------------
board = E.parse(START)[0]
E.history = {}                     # order() also reads the history heuristic
E.killers = {4: (M3, M1)}          # M3 inserted last -> newest
ordered = E.order(board, [M1, M2, M3], None, 4)
check("newest killer first", ordered[0] == M3, f"{ordered}")
check("older killer second", ordered[1] == M1, f"{ordered}")
check("non-killer last", ordered[2] == M2, f"{ordered}")

# --------------------------------------------------------------------------
# 3. Duplicate insertion: re-inserting a stored killer must not add an entry
#    and must not lose the other killer's slot.
# --------------------------------------------------------------------------
E.killers = {4: (M3, M1)}
ordered = E.order(board, [M1, M3], None, 4)
check("stored killers are not duplicated in ordering", ordered == [M3, M1],
      f"{ordered}")
check("killer slot count unchanged by ordering", len(E.killers[4]) == 2)

# --------------------------------------------------------------------------
# 4. Reordering an existing killer promotes it to the front.
# --------------------------------------------------------------------------
E.history = {}
E.killers = {4: (M1, M3)}          # M1 newest
ordered = E.order(board, [M3, M1], None, 4)
check("promoted killer sorts first", ordered[0] == M1, f"{ordered}")

# --------------------------------------------------------------------------
# 5. Storage is independent per ply.
# --------------------------------------------------------------------------
E.history = {}
E.killers = {4: (M3,), 5: (M1,)}
at4 = E.order(board, [M1, M2, M3], None, 4)
at5 = E.order(board, [M1, M2, M3], None, 5)
check("ply 4 uses ply 4 killers", at4[0] == M3, f"{at4}")
check("ply 5 uses ply 5 killers", at5[0] == M1, f"{at5}")
check("ply 6 has no killers", E.order(board, [M1, M2, M3], None, 6) == [M1, M2, M3])

# --------------------------------------------------------------------------
# 6. Per-search initialization: think() must start from empty killer state.
# --------------------------------------------------------------------------
b, s, ep, ca = E.parse(ITALIAN)
E.killers = {99: (M1, M2)}         # poison a ply a shallow search will not reach
E.TT, E.history = {}, {}
E.nodes, E.MAX_NODES = 0, 20000
legal = ["b1c3", "g1f3", "d2d4", "e2e4", "f1c4", "d1h5", "a2a3", "h2h3"]
E.think(ITALIAN, legal, "Alpha-beta, depth 4")
check("think() resets killer storage", 99 not in E.killers, f"{sorted(E.killers)}")
check("think() leaves bounded killers",
      all(len(v) <= 2 for v in E.killers.values()),
      f"worst {max((len(v) for v in E.killers.values()), default=0)}")

# --------------------------------------------------------------------------
# 7. Deterministic ordering: identical inputs give identical output.
# --------------------------------------------------------------------------
E.history = {}
E.killers = {4: (M3, M1)}
first = E.order(board, [M1, M2, M3], None, 4)
second = E.order(board, [M1, M2, M3], None, 4)
check("ordering is deterministic", first == second, f"{first} vs {second}")
E.killers = {}
check("empty killers preserve input order",
      E.order(board, [M1, M2, M3], None, 4) == [M1, M2, M3])

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("all killer-move checks passed")
