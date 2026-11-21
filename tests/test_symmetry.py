# Regression tests for positional-eval symmetry (F1: black PST orientation).
# Run: python3 tests/test_symmetry.py   (exit 0 = pass)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as E

START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
POSITIONS = [
    START,
    "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4",
    "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
    "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
    "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
]
# A white piece on d4 and the same black piece on d5 are mirror images:
# board indices 35 and 27, and 35 ^ 56 == 27.
MIRRORED_PAIRS = {
    "P": ("4k3/8/8/8/3P4/8/8/4K3 w - - 0 1", "4k3/8/8/3p4/8/8/8/4K3 w - - 0 1"),
    "N": ("4k3/8/8/8/3N4/8/8/4K3 w - - 0 1", "4k3/8/8/3n4/8/8/8/4K3 w - - 0 1"),
    "B": ("4k3/8/8/8/3B4/8/8/4K3 w - - 0 1", "4k3/8/8/3b4/8/8/8/4K3 w - - 0 1"),
    "R": ("4k3/8/8/8/3R4/8/8/4K3 w - - 0 1", "4k3/8/8/3r4/8/8/8/4K3 w - - 0 1"),
    "Q": ("4k3/8/8/8/3Q4/8/8/4K3 w - - 0 1", "4k3/8/8/3q4/8/8/8/4K3 w - - 0 1"),
}

failures = []


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        failures.append(name)


def mirror_fen(fen):
    """Rank-flipped, colour-swapped FEN (the symmetry eval must obey)."""
    placement, side, cast, ep = fen.split()[:4]
    rest = fen.split()[4:] or ["0", "1"]
    ranks = [''.join(c.swapcase() if c.isalpha() else c for c in r)
             for r in placement.split('/')[::-1]]
    side2 = 'b' if side == 'w' else 'w'
    cast2 = '-' if cast == '-' else ''.join(
        c for c in 'KQkq' if c in ''.join(x.swapcase() for x in cast))
    ep2 = '-' if ep == '-' else ep[0] + str(9 - int(ep[1]))
    return ' '.join(['/'.join(ranks), side2, cast2, ep2] + rest)


def ev(fen):
    return E.evaluate(E.parse(fen)[0])


# 1. The start position is positionally equal: nothing to prefer.
check("start position evaluates to 0", ev(START) == 0, f"got {ev(START)}")

# 2. Mirrored positions must negate (engine scores from white's view).
for fen in POSITIONS:
    a, b = ev(fen), ev(mirror_fen(fen))
    check(f"mirror negation {fen[:32]}", a == -b, f"{a} vs {b}")

# 3. Every piece type must be indifferent on a mirrored pair.
for piece, (white_fen, black_fen) in MIRRORED_PAIRS.items():
    total = ev(white_fen) + ev(black_fen)
    check(f"{piece}: white d4 + black d5 is neutral", total == 0, f"got {total}")

# 4. Bare kings are neutral (king table is rank-asymmetric, so this catches it).
check("bare kings neutral", ev("4k3/8/8/8/8/8/8/4K3 w - - 0 1") == 0,
      f"got {ev('4k3/8/8/8/8/8/8/4K3 w - - 0 1')}")

# 5. Material is preserved: a queen is worth ~900 regardless of orientation.
base = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
delta = ev("4k3/8/8/8/8/8/8/Q3K3 w - - 0 1") - ev(base)
check("queen adds ~900", 820 <= delta <= 980, f"delta {delta}")

# 6. Bishop pair still paid, and it is symmetric.
two_b = ev("4k3/8/8/8/8/8/8/2B1KB2 w - - 0 1") - ev(base)
two_b_black = ev("2b1kb2/8/8/8/8/8/8/4K3 w - - 0 1") - ev(base)
check("white bishop pair pays", 620 <= two_b <= 780, f"delta {two_b}")
check("bishop pair symmetric", abs(two_b + two_b_black) <= 40,
      f"white {two_b} black {two_b_black}")

# 7. Mop-up endgames (winning bare endgames) must also mirror-negate. The
# mop-up term drives the LOSING king to the edge, so its distance must be
# measured on whichever king is losing, not always on black's.
MOPUP_POSITIONS = [
    "8/8/3k4/8/8/8/4Q3/4K3 w - - 0 1",
    "8/8/4k3/8/8/8/8/R3K3 w - - 0 1",
    "8/8/4k3/8/8/8/8/3RKR2 w - - 0 1",
    "8/8/3k4/8/8/8/8/2B1KB2 w - - 0 1",
]
for fen in MOPUP_POSITIONS:
    a, b = ev(fen), ev(mirror_fen(fen))
    check(f"mop-up negation {fen[:32]}", a == -b and a != 0, f"{a} vs {b}")

print()
if failures:
    print(f"FAILED {len(failures)}: {failures}")
    sys.exit(1)
print("all symmetry checks passed")
