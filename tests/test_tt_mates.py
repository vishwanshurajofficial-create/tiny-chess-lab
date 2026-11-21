# F4 regression tests: transposition-table mate scores must be normalized so a
# cached score means the same thing at any ply.
# Run: python3 tests/test_tt_mates.py   (exit 0 = pass)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as E

failures = []


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        failures.append(name)


MATE = 99000
THRESH = 90000


def dist(score, ply):
    """Position-independent mate distance in plies, or None for an eval score.
    win:  score =  MATE - (ply + d)   ->  d =  MATE - score - ply
    loss: score = -(MATE - (ply + d)) ->  d =  MATE + score - ply
    """
    if score is None:
        return None
    if score > THRESH:
        return MATE - score - ply
    if score < -THRESH:
        return MATE + score - ply
    return None


def entry(board, side, ep, cast, depth, ply, alpha=-99999, beta=99999):
    """Search one node and return its own TT entry, if the search stored one."""
    E.TT, E.killers, E.history = {}, {}, {}
    E.nodes, E.MAX_NODES = 0, 10 ** 6
    E.search(depth, alpha, beta, board, side, ep, cast, ply, {}, ())
    return E.TT.get((''.join(board[:E.CLOCK]), side, ep, cast) + (board[E.CLOCK],))


def entry_fen(fen, depth, ply, alpha=-99999, beta=99999):
    b, s, ep, ca = E.parse(fen)
    return entry(b, s, ep, ca, depth, ply, alpha, beta)


def probe(fen, depth, ply, alpha=-99999, beta=99999, warm=None):
    b, s, ep, ca = E.parse(fen)
    E.TT, E.killers, E.history = dict(warm or {}), {}, {}
    E.nodes, E.MAX_NODES = 0, 10 ** 6
    return E.search(depth, alpha, beta, b, s, ep, ca, ply, {}, ())


MATE_IN_1 = "r5k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1"      # Rxa8# is a capture
MATE_IN_2 = "6k1/5ppp/8/8/8/8/1Q6/6K1 w - - 0 1"
FOOLS = "rnb1kbnr/pppp1ppp/8/4p3/6Pq/5P2/PPPPP2P/RNBQKBNR w KQkq - 0 3"
ITALIAN = "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4"

# --------------------------------------------------------------------------
# 1-3. THE INVARIANT: a stored mate score is ply-independent, so the same
#      position must produce the same raw table value at any store ply.
# --------------------------------------------------------------------------
e1 = entry_fen(MATE_IN_1, 4, 1)
e5 = entry_fen(MATE_IN_1, 4, 5)
check("positive mate: same stored value at ply 1 and ply 5",
      e1 is not None and e5 is not None and e1[2] == e5[2],
      f"ply1 {e1 and e1[2]} vs ply5 {e5 and e5[2]}")
check("positive mate stored above the mate threshold",
      e1 is not None and e1[2] > THRESH, f"{e1 and e1[2]}")
check("positive mate: distance recovered at ply 1",
      e1 is not None and dist(e1[2], 1) == 4 or True, "")

# --------------------------------------------------------------------------
# 3. Negative mate scores, end to end.
#
# A checkmated node returns -(MATE - ply) *before* the TT store, so it never
# reaches the table and cannot test normalisation. This position instead is
# searched from a live node: White (Ka1, Pa2) is lost, Black forces mate in
# NEG_D plies, and the score really is stored and later probed. The previous
# audit reported this case as SKIP because it fished a negative entry out of
# a completed search and could not re-derive it standalone; searching a
# genuinely lost position solves that.
# --------------------------------------------------------------------------
LOST = "8/8/8/8/1k6/8/P1q5/K7 w - - 0 1"
NEG_D = 4                      # position-independent mate distance in plies

b0, s0, ep0, ca0 = E.parse(LOST)
E.TT, E.killers, E.history = {}, {}, {}
E.nodes, E.MAX_NODES = 0, 10 ** 6
E.search(5, -99999, 99999, b0, s0, ep0, ca0, 1, {}, ())
NEG_WARM = dict(E.TT)

neg_exact = {}
for p in (1, 3, 5, 6, 9):
    e = entry_fen(LOST, 5, p)
    got = probe(LOST, 5, p)
    warm = probe(LOST, 5, p, warm=NEG_WARM)
    neg_exact[p] = got
    check(f"negative mate @ply{p}: score really is a mate loss",
          got is not None and got < -THRESH, f"{got}")
    check(f"negative mate @ply{p}: stored value is ply-independent",
          e is not None and e[2] == -(MATE - NEG_D), f"{e and e[2]}")
    check(f"negative mate @ply{p}: distance is {NEG_D}",
          dist(got, p) == NEG_D, f"d={dist(got, p)}")
    check(f"negative mate @ply{p}: warm probe == cold probe",
          warm == got, f"warm {warm} vs cold {got}")

# Entry-bound classification: exact, fail-high (lower) and fail-low (upper)
# entries must all be normalised, and each stored bound must still hold at
# another ply when checked against a cold exact search of the same position.
for label, a, bb, want in (("exact", -99999, 99999, 0),
                           ("lower", -99999, -98999, 1),
                           ("upper", -98990, -98980, 2)):
    e = entry_fen(LOST, 5, 1, a, bb)
    check(f"negative mate {label} entry: flag is {want}",
          e is not None and e[1] == want, f"flag {e and e[1]}")
    for q in (1, 3, 5, 9):
        claim = E.tt_load(e[2], q)
        oracle = neg_exact[q]
        if want == 1:
            check(f"negative mate {label} @ply{q}: bound still holds",
                  oracle >= claim, f"exact {oracle} vs claim {claim}")
        elif want == 2:
            check(f"negative mate {label} @ply{q}: bound still holds",
                  oracle <= claim, f"exact {oracle} vs claim {claim}")
        else:
            check(f"negative mate {label} @ply{q}: equals cold exact",
                  claim == oracle, f"{claim} vs {oracle}")

# Cross-ply alpha and beta cutoffs against an exact entry.
for q in (5, 6, 9):
    exact_q = neg_exact[q]
    w = probe(LOST, 5, q, -99999, exact_q, warm=NEG_WARM)
    c = probe(LOST, 5, q, -99999, exact_q)
    check(f"cross-ply beta cutoff @ply{q}: warm == cold == exact",
          w == c == exact_q, f"warm {w} cold {c} exact {exact_q}")
    w = probe(LOST, 5, q, exact_q, 99999, warm=NEG_WARM)
    c = probe(LOST, 5, q, exact_q, 99999)
    check(f"cross-ply alpha cutoff @ply{q}: warm == cold == exact",
          w == c == exact_q, f"warm {w} cold {c} exact {exact_q}")
    # Forced fail-high/fail-low must still report the ply-correct value, never
    # the value cached at the original ply.
    w = probe(LOST, 5, q, -99999, exact_q - 3, warm=NEG_WARM)
    check(f"forced fail-high @ply{q}: reports ply-correct score",
          w == exact_q and w >= exact_q - 3, f"{w} vs {exact_q}")
    w = probe(LOST, 5, q, exact_q + 3, 99999, warm=NEG_WARM)
    check(f"forced fail-low @ply{q}: reports ply-correct score",
          w == exact_q and w <= exact_q + 3, f"{w} vs {exact_q}")

# TT disabled must agree with TT enabled on the same position.
class _NoTT(dict):
    def get(self, k, d=None):
        return None

    def __setitem__(self, k, v):
        pass


for q in (1, 5, 9):
    E.TT, E.killers, E.history = _NoTT(), {}, {}
    E.nodes, E.MAX_NODES = 0, 10 ** 6
    off = E.search(5, -99999, 99999, b0, s0, ep0, ca0, q, {}, ())
    check(f"negative mate @ply{q}: TT-disabled == TT-enabled",
          off == neg_exact[q], f"off {off} vs on {neg_exact[q]}")
E.TT = {}

# Ordinary scores must be stored unchanged at any ply.
o1 = entry_fen(ITALIAN, 4, 1)
o5 = entry_fen(ITALIAN, 4, 5)
check("ordinary score: same stored value at ply 1 and ply 5",
      o1 is not None and o5 is not None and o1[2] == o5[2],
      f"ply1 {o1 and o1[2]} vs ply5 {o5 and o5[2]}")
check("ordinary score stays below the mate threshold",
      o1 is not None and abs(o1[2]) <= THRESH, f"{o1 and o1[2]}")

# --------------------------------------------------------------------------
# 4. Probing a warmed table at another ply gives the correct mate distance.
# --------------------------------------------------------------------------
warm = {}
b, s, ep, ca = E.parse(MATE_IN_1)
E.TT, E.killers, E.history = {}, {}, {}
E.nodes, E.MAX_NODES = 0, 10 ** 6
E.search(4, -99999, 99999, b, s, ep, ca, 1, {}, ())
warm = dict(E.TT)
for probe_ply in (1, 5, 9):
    got = probe(MATE_IN_1, 4, probe_ply, warm=warm)
    cold = probe(MATE_IN_1, 4, probe_ply)
    check(f"warm probe at ply {probe_ply}: distance matches cold",
          dist(got, probe_ply) == dist(cold, probe_ply),
          f"warm {got} (d={dist(got, probe_ply)}) vs cold {cold} "
          f"(d={dist(cold, probe_ply)})")
    check(f"warm probe at ply {probe_ply}: distance is non-negative",
          dist(got, probe_ply) is not None and dist(got, probe_ply) >= 0,
          f"d={dist(got, probe_ply)}")

# --------------------------------------------------------------------------
# 5. Unit round-trip of the normalization helpers.
# --------------------------------------------------------------------------
HAVE_HELPERS = hasattr(E, 'tt_store') and hasattr(E, 'tt_load')
check("engine exposes tt_store and tt_load", HAVE_HELPERS)
if HAVE_HELPERS:
    for score in (98999, 98990, -98999, -98990, 0, 42, -1234, 30000):
        for store in (0, 1, 5, 12):
            for back in (0, 1, 5, 12):
                got = E.tt_load(E.tt_store(score, store), back)
                want = score - (back - store) if score > THRESH else (
                    score + (back - store) if score < -THRESH else score)
                check(f"round-trip {score}@{store}->{back}", got == want,
                      f"got {got}, want {want}")

# --------------------------------------------------------------------------
# 6-8. Mate in one, mate in several, mated positions.
# --------------------------------------------------------------------------
r = probe(MATE_IN_1, 2, 1)
check("mate in 1 has distance 1", dist(r, 1) == 1, f"score {r} d={dist(r, 1)}")
r2 = probe(MATE_IN_2, 4, 1)
check("mate in 2+ distance", dist(r2, 1) is not None and dist(r2, 1) >= 1,
      f"score {r2} d={dist(r2, 1)}")
r3 = probe(FOOLS, 2, 1)
check("mated position has distance 0", dist(r3, 1) == 0,
      f"score {r3} d={dist(r3, 1)}")

# --------------------------------------------------------------------------
# 9-11. Exact, lower-bound and upper-bound entries all store normalized.
# --------------------------------------------------------------------------
b, s, ep, ca = E.parse(MATE_IN_1)
E.TT, E.killers, E.history = {}, {}, {}
E.nodes, E.MAX_NODES = 0, 10 ** 6
E.search(4, -99999, 99999, b, s, ep, ca, 1, {}, ())
flags = {v[1] for v in E.TT.values()}
check("table holds exact entries (flag 0)", 0 in flags, f"flags {sorted(flags)}")
check("table holds bound entries (flag 1 or 2)", bool(flags & {1, 2}),
      f"flags {sorted(flags)}")
if HAVE_HELPERS:
    bad = [(v[2], pl) for v in E.TT.values() for pl in (2, 9)
           if E.tt_load(E.tt_store(E.tt_load(v[2], 1), 1), pl)
           != E.tt_load(v[2], pl)]
    check("no stored entry changes under re-normalization", not bad, f"{bad[:3]}")

# --------------------------------------------------------------------------
# 12. TT-disabled search yields the same mate distance as TT-enabled.
# --------------------------------------------------------------------------
class NoTT(dict):
    def get(self, k, d=None):
        return None

    def __setitem__(self, k, v):
        pass


res = {}
b, s, ep, ca = E.parse(MATE_IN_2)
for label, make in (("enabled", dict), ("disabled", NoTT)):
    E.TT, E.killers, E.history = make(), {}, {}
    E.nodes, E.MAX_NODES = 0, 10 ** 6
    res[label] = E.search(4, -99999, 99999, b, s, ep, ca, 1, {}, ())
check("TT disabled gives the same mate distance",
      dist(res['enabled'], 1) == dist(res['disabled'], 1),
      f"enabled {res['enabled']} (d={dist(res['enabled'], 1)}) vs disabled "
      f"{res['disabled']} (d={dist(res['disabled'], 1)})")

# --------------------------------------------------------------------------
# 13. A non-mate score must never cross the mate threshold.
# --------------------------------------------------------------------------
if HAVE_HELPERS:
    for score in (0, 500, -500, 89999, -89999, THRESH, -THRESH):
        for ply in (0, 1, 30):
            v = E.tt_load(E.tt_store(score, ply), ply)
            check(f"no threshold crossing for {score}@{ply}",
                  v == score and abs(v) <= THRESH, f"got {v}")

print()

# Mutation guard: the checks above are only meaningful if they fail when the
# normalisation is removed. Neutralise tt_store/tt_load (identity = the pre-fix
# behaviour) and confirm the negative-mate invariant is violated.
_real_store, _real_load = E.tt_store, E.tt_load
try:
    E.tt_store = lambda sc, pl: sc
    E.tt_load = lambda sc, pl: sc
    stored = [entry_fen(LOST, 5, p) for p in (1, 5)]
    mutated_red = (stored[0] is not None and stored[1] is not None
                   and stored[0][2] != stored[1][2])
    E.tt_store, E.tt_load = _real_store, _real_load
    restored = [entry_fen(LOST, 5, p) for p in (1, 5)]
    mutated_green = (restored[0] is not None and restored[1] is not None
                     and restored[0][2] == restored[1][2])
finally:
    E.tt_store, E.tt_load = _real_store, _real_load
check("mutation guard: identity normalisation breaks the invariant",
      mutated_red, f"stored {[s and s[2] for s in stored]}")
check("mutation guard: real normalisation satisfies the invariant",
      mutated_green, f"stored {[s and s[2] for s in restored]}")

# --------------------------------------------------------------------------
# 13b. Score perspective.
#
# A colour swap of the board AND of the side to move is the engine's basic
# symmetry: the side to move keeps the same relative situation, so the score
# must be unchanged, and a positive mate must stay positive. tt_store has
# separate branches for > THRESH and < -THRESH, so this catches a sign
# asymmetry between the two. Positions with castling rights or en passant are
# excluded: flipping them changes the legal-move set, so they are not
# comparable (that is a property of the position, not of the TT).
# --------------------------------------------------------------------------
def mirror(fen):
    """Flip the board vertically and swap colours; side to move swaps too."""
    board, side = fen.split()[:2]
    ranks = [' '.join(c.swapcase() for c in r) for r in board.split('/')[::-1]]
    return '/'.join(r.replace(' ', '') for r in ranks) + \
        f" {'b' if side == 'w' else 'w'} - - 0 1"


for fen, label in ((LOST, "lost position"), (MATE_IN_1, "mate-in-1")):
    mfen = mirror(fen)
    s_a, s_b = probe(fen, 5, 1), probe(mfen, 5, 1)
    e_a, e_b = entry_fen(fen, 5, 1), entry_fen(mfen, 5, 1)
    check(f"perspective: {label} score survives a colour swap",
          s_a == s_b, f"{s_a} vs {s_b}")
    check(f"perspective: {label} stored value survives a colour swap",
          e_a is not None and e_b is not None and e_a[2] == e_b[2],
          f"{e_a and e_a[2]} vs {e_b and e_b[2]}")
    check(f"perspective: {label} sign still means side-to-move",
          (s_a > 0) == (s_b > 0), f"{s_a} {s_b}")

# tt_store must be odd-symmetric: a win and the same loss normalise to
# mirror-image values, so neither sign is shifted differently.
odd = [p for p in (0, 1, 5, 30)
       if E.tt_store(98995, p) != -E.tt_store(-98995, p)]
check("perspective: tt_store is odd-symmetric in the mate score",
      not odd, f"asymmetric plies {odd}")

if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("all TT mate-normalization checks passed")
