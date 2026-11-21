"""F12: halfmove clock, fifty-move and seventy-five-move draws.

Contracts under test:

  * the FEN halfmove field is parsed into the position and survives a
    FEN round-trip;
  * make() resets the clock on pawn moves, captures, en passant and
    promotions, and increments it on every other legal move;
  * the clock belongs to the position, so one branch of the tree can never
    contaminate a sibling;
  * a clock at or over 100 halfmoves scores as a draw, and 150 likewise -
    but a checkmated side still scores as mated;
  * repetition identity excludes the clock (FIDE counts positions, not
    clocks) while the transposition table identity includes it, so a score
    earned at one clock is never served for another;
  * selection stays deterministic and survives budget interruption.

No FEN serializer is shipped: the protocol never emits FEN, so the test
builds one from engine state to prove the state is faithfully reconstructible
rather than paying bytes for dead code.
"""
import os
import subprocess
import sys

sys.path.insert(0, '.')
import engine as E

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
QUIET = "8/8/8/3p4/8/4N3/8/4K2k w - - 7 20"      # white to move, no clock events
CAPTURE = "8/8/8/3p4/4N3/8/8/4K2k w - - 7 20"    # Ne4xd5 captures
EP = "8/8/8/3pP3/8/8/8/4K2k w - d6 7 30"         # exd6 e.p.
PROMO = "8/4P3/8/8/8/8/8/4K2k w - - 9 40"        # e8=Q promotes
DRAWABLE = "8/8/8/4k3/8/8/4P3/4K3 w - - 100 60"  # 6 legal moves, clock 100
MATE = "8/8/8/8/8/5k2/6q1/7K w - - 100 60"       # checkmated with clock 100

P99_NOQUIET = "3q4/8/8/8/8/8/PPk5/K7 w - - 99 60"   # losing, only pawn moves
P99_QUIET = "8/8/8/4k3/8/8/4P3/4K3 w - - 99 60"
P99_QUIET_LOSE = "3q4/8/2k5/8/8/8/4P3/4K3 w - - 99 60"   # lost, quiet move in hand
P98_LOSE = "4q3/8/8/3k4/8/8/4P3/4K3 w - - 98 60"         # same, one halfmove short
P100_WIN = "8/8/8/4k3/8/8/4P3/4K3 w - - 100 60"
P100_LOSE = "3q4/8/2k5/8/8/8/4P3/4K3 w - - 100 60"
P149 = "8/8/8/4k3/8/8/4P3/4K3 w - - 149 90"
P149_MATE = "7k/8/6K1/8/8/8/8/R7 w - - 149 75"      # Ra8# lands on clock 150
P150 = "8/8/8/4k3/8/8/4P3/4K3 w - - 150 90"
P150_MATE = "8/8/8/8/8/5k2/6q1/7K w - - 150 90"
P150_STALE = "7k/5Q2/8/8/8/8/8/K7 b - - 150 90"

failures = []


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        failures.append(name)


def clock(board):
    """The halfmove clock carried by the position."""
    return board[E.CLOCK]


def reset(board=None):
    E.TT, E.killers, E.history = {}, {}, {}
    E.nodes, E.MAX_NODES = 0, 10 ** 6


def to_fen(board, side, ep, castle, hm, full=1):
    """Serialize engine state back to FEN (test-side only)."""
    rows = []
    for r in range(8):
        row, empty = '', 0
        for f in range(8):
            ch = board[21 + r * 10 + f]
            if ch == '.':
                empty += 1
                continue
            if empty:
                row += str(empty)
                empty = 0
            row += ch
        rows.append(row + (str(empty) if empty else ''))
    rights = ''.join(c for c, bit in zip('KQkq', (1, 2, 4, 8)) if castle & bit)
    ep_txt = '-' if not ep else 'abcdefgh'[(ep - 21) % 10] + str(8 - (ep - 21) // 10)
    return ' '.join(['/'.join(rows), 'wb'[side], rights or '-', ep_txt,
                     str(hm), str(full)])


print("A. the FEN halfmove field is parsed into the position")
for fen, want in ((START, 0), (QUIET, 7), (DRAWABLE, 100), ("8/8/8/8/8/8/8/K6k w - - 99 51", 99)):
    b, s, ep, ca = E.parse(fen)
    check(f"clock {want} parsed", clock(b) == want, f"got {clock(b)}")
b, s, ep, ca = E.parse("8/8/8/8/8/8/8/K6k w - -")
check("a short FEN defaults the clock to 0", clock(b) == 0, f"got {clock(b)}")

print("\nB. FEN round-trip preserves the clock and the rest of the state")
for fen in (START, QUIET, CAPTURE, EP, PROMO, DRAWABLE):
    b, s, ep, ca = E.parse(fen)
    text = to_fen(b, s, ep, ca, clock(b))
    b2, s2, ep2, ca2 = E.parse(text)
    same = (b2[:120] == b[:120] and s2 == s and ep2 == ep and ca2 == ca
            and clock(b2) == clock(b))
    check(f"round-trip {fen.split()[0][:12]}..", same, text)

print("\nC. reset events clear the clock")
b, s, ep, ca = E.parse(QUIET)
nb = E.make(b, s, ep, ca, (E.square('e3'), E.square('f5'), ''))[0]
check("a quiet knight move increments", clock(nb) == 8, f"got {clock(nb)}")
b, s, ep, ca = E.parse(START)
nb = E.make(b, s, ep, ca, (E.square('e2'), E.square('e4'), ''))[0]
check("a double pawn push resets", clock(nb) == 0, f"got {clock(nb)}")
b, s, ep, ca = E.parse(CAPTURE)
nb = E.make(b, s, ep, ca, (E.square('e4'), E.square('d5'), ''))[0]
check("a capture resets", clock(nb) == 0, f"got {clock(nb)}")
b, s, ep, ca = E.parse(EP)
nb = E.make(b, s, ep, ca, (E.square('e5'), E.square('d6'), ''))[0]
check("an en passant capture resets", clock(nb) == 0, f"got {clock(nb)}")
b, s, ep, ca = E.parse(PROMO)
nb = E.make(b, s, ep, ca, (E.square('e7'), E.square('e8'), 'q'))[0]
check("a promotion resets", clock(nb) == 0, f"got {clock(nb)}")
b, s, ep, ca = E.parse("8/8/8/8/8/8/8/K6k b - - 41 60")
nb = E.make(b, s, ep, ca, (E.square('a1'), E.square('b1'), ''))[0]
check("a king move increments", clock(nb) == 42, f"got {clock(nb)}")

print("\nD. the clock is per-position: siblings cannot contaminate each other")
b, s, ep, ca = E.parse(QUIET)
brother = E.make(b, s, ep, ca, (E.square('e3'), E.square('f5'), ''))[0]
sister = E.make(b, s, ep, ca, (E.square('e3'), E.square('g4'), ''))[0]
pawn = E.make(b, s, ep, ca, (E.square('a1'), E.square('a2'), ''))[0]
check("first sibling sees parent+1", clock(brother) == 8, f"got {clock(brother)}")
check("second sibling is unaffected", clock(sister) == 8, f"got {clock(sister)}")
check("parent is unchanged after two makes", clock(b) == 7, f"got {clock(b)}")
check("a different child gets its own value", clock(pawn) in (0, 8),
      f"got {clock(pawn)}")
b, s, ep, ca = E.parse(START)
first = E.make(b, s, ep, ca, (E.square('g1'), E.square('f3'), ''))[0]
second = E.make(b, s, ep, ca, (E.square('b1'), E.square('c3'), ''))[0]
third = E.make(b, s, ep, ca, (E.square('e2'), E.square('e4'), ''))[0]
check("quiet child 1 = 1", clock(first) == 1, f"got {clock(first)}")
check("quiet child 2 = 1 (not 2)", clock(second) == 1, f"got {clock(second)}")
check("pawn child = 0", clock(third) == 0, f"got {clock(third)}")

print("\nE. fifty-move rule is a CLAIM, seventy-five-move rule is AUTOMATIC")


def value(fen, depth=3):
    reset()
    b, s, ep, ca = E.parse(fen)
    return E.search(depth, -99999, 99999, b, s, ep, ca, 1, {}, ())


# 9.3.1 needs a quiet (non-pawn, non-capture) move in hand at clock 99.
b, s, ep, ca = E.parse(P99_NOQUIET)
check("99 without a quiet move: no claim is on offer",
      not [m for m in E.gen(b, s, ep, ca)
           if b[m[0]] not in 'Pp' and b[m[1]] == '.'],
      f"{[m for m in E.gen(b, s, ep, ca)]}")
got = value(P99_NOQUIET)
check("99 without a quiet move scores the real (losing) value, not a draw",
      got < 0, f"score {got}")
b, s, ep, ca = E.parse(P99_QUIET)
check("99 with a quiet move: a claim is offered",
      bool([m for m in E.gen(b, s, ep, ca)
            if b[m[0]] not in 'Pp' and b[m[1]] == '.']))
check("99 with a quiet move cannot score below a draw", value(P99_QUIET) >= 0,
      f"score {value(P99_QUIET)}")
got = value(P99_QUIET_LOSE)
check("99 + quiet move in a lost position claims the draw (9.3.1)", got == 0,
      f"score {got}")
got = value(P98_LOSE)
check("98 is one halfmove short: still no claim, so the loss stands", got < 0,
      f"score {got}")
got = value(P98_LOSE.replace(" 98 ", " 99 "))
check("the same position one halfmove later can claim", got == 0,
      f"score {got}")
# 9.3.2: claiming from the position.
got = value(P100_WIN)
check("100 in a winnable position prefers the continuation to the claim",
      got > 0, f"score {got}")
got = value(P100_LOSE)
check("100 in a lost position takes the claim", got == 0, f"score {got}")
check("100 still returns a legal move rather than resigning",
      E.think(P100_LOSE, ["e2e3", "e2e4", "e1f1", "e1f2"], "depth 3")
      in ("e2e3", "e2e4", "e1f1", "e1f2"))
# 9.6.2: 75 moves each is automatic, so 149 must still be played out.
got = value(P149)
check("149 is not a draw yet: the pawn move resets and plays on", got > 0,
      f"score {got}")
b, s, ep, ca = E.parse(P149)
quiet_child = E.make(b, s, ep, ca, (E.square('e1'), E.square('d1'), ''))[0]
check("149 + quiet move reaches clock 150", quiet_child[E.CLOCK] == 150,
      f"{quiet_child[E.CLOCK]}")
check("a quiet move into 150 is scored as the automatic draw",
      E.search(3, -99999, 99999, quiet_child, 1, 0, 0, 1, {}, ()) == 0)
pawn_child = E.make(b, s, ep, ca, (E.square('e2'), E.square('e3'), ''))[0]
check("149 + pawn move resets the clock", pawn_child[E.CLOCK] == 0,
      f"{pawn_child[E.CLOCK]}")
# 9.6.2: "If the last move resulted in checkmate, that shall take precedence."
got = value(P149_MATE)
check("a mate landing exactly on 150 beats the automatic draw", got > 90000,
      f"score {got}")
got = value(P150)
check("150 with legal moves is the automatic draw", got == 0, f"score {got}")
got = value(P150_MATE)
check("checkmate at 150 is still a mate", got == -98999, f"score {got}")
got = value(P150_STALE)
check("stalemate at 150 is a draw", got == 0, f"score {got}")
# Past both thresholds the rules must not degrade into each other.
got = value("8/8/8/4k3/8/8/4P3/4K3 w - - 200 140")
check("200 with legal moves is still the automatic draw", got == 0, f"score {got}")
got = value("8/8/8/8/8/5k2/6q1/7K w - - 200 140")
check("a mate at 200 is still a mate", got == -98999, f"score {got}")
got = value("7k/5Q2/8/8/8/8/8/K7 b - - 200 140")
check("a stalemate at 200 is still a draw", got == 0, f"score {got}")
got = value("8/8/8/4k3/8/8/4P3/4K3 w - - 0 60")
check("clock 0 plays on normally", got > 0, f"score {got}")

print("\nF. a mate at the fifty-move limit is still a mate")
reset()
b, s, ep, ca = E.parse(MATE)
check("position really is checkmate", E.gen(b, s, ep, ca) == []
      and E.attacked(b, b.index('K'), 1))
got = E.search(3, -99999, 99999, b, s, ep, ca, 1, {}, ())
check("checkmate outranks the claim", got == -98999, f"score {got}")
reset()
b, s, ep, ca = E.parse("7k/5Q2/8/8/8/8/8/K7 b - - 100 60")
got = E.search(3, -99999, 99999, b, s, ep, ca, 1, {}, ())
check("stalemate at the limit is still 0", got == 0, f"score {got}")
reset()
b, s, ep, ca = E.parse("8/8/8/8/8/8/8/K6k w - - 100 60")
check("king against king stays ~0", abs(E.evaluate(b)) < 60, f"{E.evaluate(b)}")

print("\nG. repetition identity ignores the clock; the TT identity does not")
f0 = "8/8/8/4k3/8/8/4P3/4K3 w - - 0 60"
f99 = "8/8/8/4k3/8/8/4P3/4K3 w - - 99 60"
f99b = "8/8/8/8/4k3/8/4P3/4K3 w - - 99 60"
b0, s0, e0, c0 = E.parse(f0)
b99, s99, e99, c99 = E.parse(f99)
b99b, s99b, e99b, c99b = E.parse(f99b)
check("same position at clock 0 and 99 shares one identity",
      E.pkey(b0, s0, e0, c0) == E.pkey(b99, s99, e99, c99))
check("a different position keeps a different identity",
      E.pkey(b0, s0, e0, c0) != E.pkey(b99b, s99b, e99b, c99b))

print("\nH. the transposition table never serves a score across clocks")
reset()
b, s, ep, ca = E.parse(f0)
E.search(3, -99999, 99999, b, s, ep, ca, 1, {}, ())
cold = E.nodes
snapshot = dict(E.TT)
check("entries are keyed with the clock", E.pkey(b, s, ep, ca) + (0,) in E.TT,
      f"{sorted(k[-1] for k in E.TT)}")
check("every entry carries a clock",
      all(len(k) == 5 and isinstance(k[-1], int) for k in E.TT))
# An exact verdict only returns immediately when the window is closed, so a
# beta below the known score is what proves the cache was actually served.
reset()
E.TT.update(snapshot)
b, s, ep, ca = E.parse(f0)
got = E.search(3, -99999, 59, b, s, ep, ca, 1, {}, ())
check("the same clock serves the cached verdict", E.nodes == 1 and got == 60,
      f"{E.nodes} nodes, score {got}")
reset()
E.TT.update(snapshot)
b, s, ep, ca = E.parse(f99)
got = E.search(3, -99999, 59, b, s, ep, ca, 1, {}, ())
check("a different clock re-searches instead of reusing clock 0",
      E.nodes > 1, f"{E.nodes} nodes, score {got} (cold was {cold})")
reset()
E.TT.update(snapshot)
b, s, ep, ca = E.parse(P150)
got = E.search(3, -99999, 99999, b, s, ep, ca, 1, {}, ())
check("a cached win never survives into the automatic draw", got == 0,
      f"score {got}")
check("...because 9.6.2 returns before any table probe", E.nodes == 1,
      f"{E.nodes} nodes")
reset()
b, s, ep, ca = E.parse(P100_WIN)
check("a claimable clock still keeps the winning continuation",
      E.search(3, -99999, 99999, b, s, ep, ca, 1, {}, ()) > 0)

print("\nI. the clock is threaded through the real search")
reset()
b, s, ep, ca = E.parse(QUIET)
E.search(4, -99999, 99999, b, s, ep, ca, 1, {}, ())
clocks = {k[-1] for k in E.TT if isinstance(k, tuple) and isinstance(k[-1], int)}
check("search visits several clocks", len(clocks) > 1, f"clocks {sorted(clocks)}")
check("no visited clock goes negative", min(clocks) >= 0, f"min {min(clocks)}")

print("\nJ. think() keeps the clock consistent with the FEN it was given")
reset()
b, s, ep, ca = E.parse(QUIET)
legal = [u for u in ("e3f5", "e3g4", "e3d1", "e3c2", "e3c4", "e3d5", "e3g2",
                     "e3f1", "e3g1")]
move = E.think(QUIET, legal, "depth 3")
check("a legal move comes back", move in legal, f"{move}")
reset()
move = E.think(DRAWABLE, ["e2e3", "e2e4", "e1d1"], "depth 3")
check("a drawn game still returns a legal move", move in ("e2e3", "e2e4", "e1d1"), f"{move}")

print("\nK. interruption safety")
reset()
E.MAX_NODES = 50
try:
    b, s, ep, ca = E.parse(START)
    got = E.search(12, -99999, 99999, b, s, ep, ca, 1, {}, ())
    raised = False
except E.Budget:
    raised = True
check("the budget still interrupts a long search", raised)
reset()
E.MAX_NODES = 40
move = E.think(START, ["a2a3", "b2b3", "g1f3"], "Alpha-beta, 1,000 nodes")
check("think() survives interruption with a legal move", move in ("a2a3", "b2b3", "g1f3"),
      f"{move}")

print("\nL. determinism across hash seeds")
moves = []
for seed in ("1", "7", "2024"):
    env = dict(os.environ, PYTHONHASHSEED=seed)
    out = subprocess.run(
        [sys.executable, "-c",
         "import sys;sys.path.insert(0,'.');import engine as E;"
         "print(E.think('r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4',"
         "['f3e5','c4f7','f3g5','d2d4','b1c3'],'Alpha-beta, depth 3'))"],
        capture_output=True, text=True, env=env)
    moves.append(out.stdout.strip())
check("all seeds pick the same move", len(set(moves)) == 1, f"{moves}")

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("all halfmove checks passed")
