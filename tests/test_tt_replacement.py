"""F6: transposition-table replacement tests.

Written against the CURRENT last-write-wins policy so the deep-entry cases fail
before the fix.

Method: a synthetic entry is seeded for the root key, a real search then tries
to store over it, and the surviving entry is inspected. Retention is detected
by exact equality with the seeded entry, so a check cannot pass by coincidence.

Seeded scores are chosen not to perturb the search: a lower bound below beta
and an upper bound above alpha, so the probe does not cut off before the store
and the replacement rule is genuinely exercised.
"""
import sys
sys.path.insert(0, '.')
import engine as E

MATE = 99000
THRESH = 90000
ITAL = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"
MATE_IN_1 = "r5k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"
SENT_MOVE = (21, 22, '')       # a1b1: illegal in ITAL, so no real search picks it
WIN = 12345                    # sentinel score for a full-window store
LOW = -60000                   # lower bound below any tested beta
HIGH = 60000                   # upper bound above any tested alpha

failures = []


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        failures.append(name)


def key_of(fen):
    b, s, ep, ca = E.parse(fen)
    return (''.join(b[:E.CLOCK]), s, ep, ca) + (b[E.CLOCK],)


def seed(fen, ent):
    E.TT, E.killers, E.history = {key_of(fen): ent}, {}, {}
    E.nodes, E.MAX_NODES = 0, 10 ** 6


def store(fen, depth, ply=1, alpha=-99999, beta=99999, keep=False):
    """Search once; return the entry left in the table for that position."""
    b, s, ep, ca = E.parse(fen)
    E.killers, E.history = {}, {}
    E.nodes, E.MAX_NODES = 0, 10 ** 6
    E.search(depth, alpha, beta, b, s, ep, ca, ply, {}, ())
    return E.TT.get(key_of(fen))


def attempt(ent, depth, **kw):
    seed(ITAL, ent)
    return store(ITAL, depth, **kw)


print("1. deep entry followed by a shallow store")
SEED1 = (6, 0, WIN, SENT_MOVE)
got = attempt(SEED1, 1)
check("deep entry is not evicted by a shallower one", got == SEED1, f"{got}")

print("\n2. shallow entry followed by a deep store")
got = attempt((1, 0, WIN, SENT_MOVE), 6)
check("deep entry replaces a shallow one",
      got is not None and got[0] == 6, f"depth {got and got[0]}")
check("the replacement carries the fresh result",
      got != (1, 0, WIN, SENT_MOVE), f"{got}")

print("\n3. exact entry versus non-exact entry")
SEED3a = (6, 1, LOW, SENT_MOVE)               # deep lower bound
got = attempt(SEED3a, 3)
check("a deep non-exact entry survives a shallow search",
      got == SEED3a, f"{got}")
SEED3b = (6, 0, 0, SENT_MOVE)                 # deep exact
got = attempt(SEED3b, 2)
check("a deep exact entry survives a shallow search", got == SEED3b, f"{got}")

print("\n4. lower-bound entry (fail-high store)")
SEED4 = (6, 1, LOW, SENT_MOVE)
got = attempt(SEED4, 2, alpha=-99999, beta=-5000)
check("deep lower bound survives a shallow fail-high", got == SEED4, f"{got}")

print("\n5. upper-bound entry (fail-low store)")
SEED5 = (6, 2, HIGH, SENT_MOVE)
got = attempt(SEED5, 2, alpha=9000, beta=99999)
check("deep upper bound survives a shallow fail-low", got == SEED5, f"{got}")

print("\n6. equal-depth store")
SEED6 = (3, 1, 0, SENT_MOVE)
got = attempt(SEED6, 3)
check("an equal-depth result still replaces the entry", got != SEED6, f"{got}")
check("equal-depth replacement keeps the depth",
      got is not None and got[0] == 3, f"depth {got and got[0]}")
check("equal-depth replacement takes the new best move",
      got is not None and got[3] != SENT_MOVE, f"move {got and got[3]}")

print("\n7. replacement at different search plies")
E.TT, E.killers, E.history = {}, {}, {}
deep = store(ITAL, 6, ply=1)
check("deep entry stored at ply 1", deep is not None and deep[0] == 6,
      f"depth {deep and deep[0]}")
got = store(ITAL, 2, ply=5)
check("a shallow store at ply 5 does not evict the ply-1 deep entry",
      got is not None and got[0] == 6, f"depth {got and got[0]}")

print("\n8. mate-score normalization through replacement")
E.TT, E.killers, E.history = {}, {}, {}
m1 = store(MATE_IN_1, 6, ply=1)
check("mate entry stored", m1 is not None and abs(m1[2]) > THRESH,
      f"{m1 and m1[2]}")
got = store(MATE_IN_1, 1, ply=5)
check("a shallow store does not evict a mate entry",
      got is not None and abs(got[2]) > THRESH, f"{got and got[2]}")
check("retained mate score is still ply-independent",
      got is not None and got[2] == m1[2], f"{got and got[2]} vs {m1[2]}")
check("mate distance still recoverable from the retained entry",
      got is not None and MATE - E.tt_load(got[2], 5) - 5 == 1,
      f"d={None if not got else MATE - E.tt_load(got[2], 5) - 5}")

print("\n9. best-move preservation")
SEED9 = (6, 0, WIN, SENT_MOVE)
got = attempt(SEED9, 1)
check("the retained entry keeps its best move",
      got is not None and got[3] == SENT_MOVE, f"move {got and got[3]}")

print("\n10. deterministic replacement")


def sequence():
    E.TT, E.killers, E.history = {}, {}, {}
    return [store(ITAL, d) for d in (6, 1, 4, 2, 6, 3)]


a, b = sequence(), sequence()
check("the same store sequence yields the same table", a == b)
check("the table never ends shallower than its deepest store",
      a[-1] is not None and a[-1][0] == 6, f"final depth {a[-1] and a[-1][0]}")

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("all TT replacement checks passed")
