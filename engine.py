# tiny-chess-01 engine source (MIT), packed by `makefun compress` into
# main.py. 120-square mailbox. Negamax alpha-beta + quiescence, TT with
# bounds flags, TT/MVV-LVA/killer ordering, material + PST eval with
# middlegame/endgame king tables + bishop pair. Fixed node budget per
# move (scaled by opponent), never a wall clock: replays byte for byte.
# Tables: tests/gen_tables.py.
#
# Halfmove clock (F12): it rides at board[CLOCK], inside the position that
# make() copies, so every branch owns its own value and no call site can
# forget it. A pawn move or capture resets it, anything else advances it.
# Article 9.3 (fifty moves) is a CLAIM by the side to move, so it is modelled
# as an extra zero-valued choice: a floor on the score, never a forced result.
# Article 9.6.2 (seventy-five moves) is automatic, and a mate delivered by the
# last move takes precedence over it. Repetition identity (pkey) excludes the
# clock; transposition identity includes it.
import json
import os
import sys
import urllib.request as U

ENV = os.environ.get("MAKEFUN_ENV_URL")
KNIGHT = 8, 12, 19, 21, -8, -12, -19, -21
KING = 1, 9, 10, 11, -1, -9, -10, -11
VALUE = {'P': 100, 'N': 320, 'B': 330, 'R': 500, 'Q': 900, 'K': 0}
# board[CLOCK] carries the halfmove clock. Keeping it inside the position (the
# list make() copies) means every branch owns its own clock: no sibling or
# parent can be contaminated, and no call site can forget to thread it.
CLOCK = 120
# rights bit, king from/to, empties, safe squares, attacker side.
CASTLE = (
    (1, 95, 97, (96, 97, 96), (95, 96, 97), 1),   # white O-O
    (2, 95, 93, (92, 93, 94), (95, 94, 94), 1),   # white O-O-O
    (4, 25, 27, (26, 27, 26), (25, 26, 27), 0),   # black O-O
    (8, 25, 23, (22, 23, 24), (25, 24, 24), 0),   # black O-O-O
)
# x5-scaled PSTs, chr(v//5 + 80), bonus = (ord(c) - 80) * 5; order
# P N B R Q, king middlegame, king endgame. Black mirrors with i ^ 56.
PST = (
    "PPPPPPPPZZZZZZZZRRTVVTRRQQRUURQQPPPTTPPPQONPPNOQQRRLLRRQPPPPPPPP"
    "FHJJJJHFHLPPPPLHJPRSSRPJJQSTTSQJJPSTTSPJJQRSSRQJHLPQQPLHFHJJJJHF"
    "LNNNNNNLNPPPPPPNNPQRRQPNNQQRRQQNNPRRRRPNNRRRRRRNNQPPPPQNLNNNNNNL"
    "PPPPPPPPQRRRRRRQOPPPPPPOOPPPPPPOOPPPPPPOOPPPPPPOOPPPPPPOPPPQQPPP"
    "LNNOONNLNPPPPPPNNPQQQQPNOPQQQQPOPPQQQQPONQQQQQPNNPQPPPPNLNNOONNL"
    "JHHFFHHJJHHFFHHJJHHFFHHJJHHFFHHJLJJHHJJLNLLLLLLNTTPPPPTTTVRPPRVT"
    "FHJLLJHFJLNPPNLJJNTVVTNJJNVXXVNJJNVXXVNJJNTVVTNJJJPPPPJJFJJJJJJF"
)
# Node budget per opponent, inside the 10s/move and 1800s/trial caps.
# The env's opponent_name is prose ("Alpha-beta, depth 2", "Alpha-beta,
# 500,000 nodes"); budget_for resolves it by substring, no silent mismatch.
BUDGET = (('2,000,000', 150000), ('1,000,000', 150000),
          ('500,000', 130000), ('250,000', 90000), ('100,000', 60000),
          ('depth 4', 35000), ('depth 3', 20000), ('depth 2', 10000))
MAX_NODES = 30000
EXT_PLY = 16  # check extensions stop past this ply, so depth must fall
nodes = 0
TT = {}
killers = {}
history = {}


def budget_for(opponent):
    n = opponent.replace('-', ' ')
    for s, v in BUDGET:
        if s in n:
            return v
    return 60000  # unknown opponent: a safe middle budget


class Budget(Exception):
    pass


def square(u):
    """Algebraic square like 'e2' -> mailbox index."""
    return 21 + (8 - int(u[1])) * 10 + ord(u[0]) - 97


def parse(fen):
    """FEN -> (board, side, ep square, castling bits)."""
    placement, side, castling, ep, *rest = fen.split()
    board = list(' ' * 20 + (' ' + '.' * 8 + ' ') * 8 + ' ' * 20)
    rank = file = 0
    for ch in placement:
        if ch == '/':
            rank += 1
            file = 0
        elif ch.isdigit():
            file += int(ch)
        else:
            board[21 + rank * 10 + file] = ch
            file += 1
    ep_sq = 0 if ep == '-' else square(ep)
    bits = 0
    for i, ch in enumerate('KQkq'):
        if ch in castling:
            bits |= 1 << i
    board.append(int(rest[0]) if rest else 0)
    return board, 0 if side == 'w' else 1, ep_sq, bits


def attacked(board, sq, by):
    """Is square sq attacked by side `by`?"""
    F = ('KQRBNP', 'kqrbnp')[by]
    if F[4] in [board[sq + o] for o in KNIGHT]:
        return 1
    if F[0] in [board[sq + o] for o in KING]:
        return 1
    pawn_from = (-9, -11) if by else (9, 11)
    if F[5] in [board[sq + o] for o in pawn_from]:
        return 1
    for d in (1, 10, 9, 11):
        for step in (d, -d):
            t = sq + step
            while board[t] == '.':
                t += step
            c = board[t]
            ray = F[2] if d % 9 == 1 else F[3]  # (1,10) rook rays, else bishop
            if c == F[1] or c == ray:
                return 1
    return 0


def make(board, side, ep, castle, move):
    """Apply (from, to, promo) -> (new board, new ep, new castle)."""
    p, t, promo = move
    c = board[p]
    nb = board[:]
    # Fifty-move clock: a pawn move or any capture resets it, anything else
    # advances it. Promotions and en passant are pawn moves, so this single
    # test covers every reset event.
    nb[CLOCK] = 0 if c in 'Pp' or board[t] != '.' else board[CLOCK] + 1
    nb[p] = '.'
    nb[t] = (promo.upper(), promo)[side] if promo else c
    if c in 'Kk':
        castle &= (12, 3)[side]
        if t - p == 2:        # kingside: rook h->f
            nb[t - 1] = nb[t + 1]
            nb[t + 1] = '.'
        elif t - p == -2:     # queenside: rook a->d
            nb[t + 1] = nb[t - 2]
            nb[t - 2] = '.'
    for q, bit in ((98,1),(91,2),(28,4),(21,8)):
        if p == q or t == q:
            castle &= ~bit
    ep2 = 0
    if c in 'Pp':
        if abs(t - p) == 20:
            ep2 = p + t >> 1
        elif t == ep and p % 10 != t % 10:
            nb[t + (10, -10)[side]] = '.'  # en passant: remove victim
    return nb, ep2, castle


def gen(board, side, ep, castle, captures_only=0):
    """Legal moves as (from, to, promo) tuples."""
    ms = []
    for p in range(21, 99):
        z = board[p]
        if z in '. ' or z.isupper() != (side == 0):
            continue
        u = z.upper()
        if u == 'P':
            d = (-10, 10)[side]
            t = p + d
            if board[t] == '.':
                if t < 29 or t > 90:  # promotion rank
                    ms += [(p, t, x) for x in 'qrbn']
                elif not captures_only:
                    ms.append((p, t, ''))
                    start = (31 <= p <= 38) if side else (81 <= p <= 88)
                    if start and board[t + d] == '.':
                        ms.append((p, t + d, ''))
            for o in (d - 1, d + 1):
                t = p + o
                z = board[t]
                if z == ' ':
                    continue
                if z == '.':
                    if t == ep:
                        ms.append((p, t, ''))
                elif z.isupper() != (side == 0):
                    if t < 29 or t > 90:
                        ms += [(p, t, x) for x in 'qrbn']
                    else:
                        ms.append((p, t, ''))
        elif u in 'NK':
            for o in (KNIGHT if u == 'N' else KING):
                t = p + o
                z = board[t]
                if z == ' ':
                    continue
                if z == '.':
                    captures_only or ms.append((p, t, ''))
                elif z.isupper() != (side == 0):
                    ms.append((p, t, ''))
            if u == 'K' and not captures_only:
                for bit, f0, f1, empty, safe, by in CASTLE:
                    if (castle & bit and f0 == p
                            and board[empty[0]] == board[empty[1]] == board[empty[2]] == '.'
                            and not attacked(board, safe[0], by)
                            and not attacked(board, safe[1], by)
                            and not attacked(board, safe[2], by)):
                        ms.append((f0, f1, ''))
        else:
            dirs = ((1, 10) if u == 'R' else
                    (9, 11) if u == 'B' else (1, 9, 10, 11))
            for d in dirs:
                for step in (d, -d):
                    t = p + step
                    while board[t] == '.':
                        captures_only or ms.append((p, t, ''))
                        t += step
                    z = board[t]
                    if z != ' ' and z.isupper() != (side == 0):
                        ms.append((p, t, ''))
    return [m for m in ms
            if not attacked((nb := make(board, side, ep, castle, m)[0]),
                            nb.index('K' if side == 0 else 'k'), 1 - side)]


def evaluate(board):
    """Static eval from white's view: material + PST + bishop pair."""
    score = phase = 0
    kings = []
    for p in range(21, 99):
        z = board[p]
        if z in '. ':
            continue
        u = z.upper()
        sign = 1 - 2 * (z > 'Z')
        i = (p - 21) // 10 * 8 + (p - 21) % 10
        if z > 'Z':
            i ^= 56  # tables are white-perspective: flip the rank for black
        if u == 'K':
            kings.append((i, sign))
            continue
        score += sign * ((ord(PST[64 * 'PNBRQ'.index(u) + i]) - 80) * 5
                         + VALUE[u])
        if u != 'P':
            phase += VALUE[u]
    king_base = 320 if phase > 2400 else 384  # middlegame vs endgame table
    for i, sign in kings:
        score += sign * (ord(PST[king_base + i]) - 80) * 5
    pair = (board.count('B') > 1) - (board.count('b') > 1)
    score += 30 * pair
    # Mop-up: with a winning margin in a bare endgame, bring the winning
    # king across the board and drive the losing king to the edge so
    # mates are found instead of drifting.
    if len(kings) == 2 and abs(score) > 800 and phase < 2600:
        iw = ib = 0
        for i, s in kings:
            if s > 0:
                iw = i
            else:
                ib = i
        d = abs(iw % 8 - ib % 8) + abs(iw // 8 - ib // 8)
        lk = ib if score > 0 else iw  # edge distance of the LOSING king
        e = min(lk % 8, 7 - lk % 8, lk // 8, 7 - lk // 8)
        m = 6 * (14 - d) + 3 * (3 - e)
        score += m if score > 0 else -m
    return score


def tt_store(score, ply):
    """A mate score is stored as a mate distance, not a ply-dependent value,
    so probing it at any other ply re-anchors correctly."""
    return (score + ply if score > 90000 else
            score - ply if score < -90000 else score)


def tt_load(score, ply):
    """Undo tt_store: turn a stored mate distance back into a score at `ply`."""
    return tt_store(score, -ply)


def order(board, ms, tt_move, ply):
    """TT move first, then MVV-LVA captures, killers, then history."""
    def key(m):
        if m == tt_move:
            return (0,)
        victim = board[m[1]]
        if victim not in '._ ':
            return (1, -(VALUE[victim.upper()] * 100 - VALUE[board[m[0]].upper()]))
        k = killers.get(ply, ())
        if m in k:
            return (2, k.index(m))  # newest killer keeps priority
        return (3, -history.get((board[m[0]], m[1]), 0))
    ms.sort(key=key)
    return ms


def pkey(b, s, ep, c):
    """Repetition identity: placement + side + castling, and en passant only
    when a legal en-passant capture exists, so unusable or pinned ep rights do
    not make two identical positions look different."""
    return (''.join(b[:CLOCK]), s, ep if ep and any(m[1] == ep for m in gen(b, s, ep, c, 1)) else 0, c)


def search(depth, alpha, beta, board, side, ep, castle, ply, hist, path,
           null=0):
    """Negamax alpha-beta with null-move pruning (R=2), LMR and a check
    extension; quiescence at depth 0. Raises Budget."""
    global nodes
    nodes += 1
    if nodes >= MAX_NODES:
        raise Budget
    in_check = attacked(board, board.index('K' if side == 0 else 'k'), 1 - side)
    clk = board[CLOCK]
    # 9.6.2: seventy-five moves each is drawn automatically. 9.3: fifty moves
    # each gives the side to move the OPTION of a draw, either from the
    # position or by declaring a quiet move that would bring the count to 100.
    # Both need a legal move to be on the table, and neither outranks a mate,
    # so a side with no legal move falls through to the mate/stalemate handling
    # below and checkmate keeps precedence at either threshold.
    clm = 0
    if clk > 99:
        if not gen(board, side, ep, castle):
            return -(99000 - ply) if in_check else 0
        if clk > 149:
            return 0
        clm = 1
    elif clk == 99 and any(
            board[m[0]] not in 'Pp' and board[m[1]] == '.'
            for m in gen(board, side, ep, castle)):
        clm = 1
    # Claiming is a choice, so it is a floor on the score and not a return: a
    # side with a better continuation simply plays it.
    if clm:
        alpha = max(alpha, 0)
        if alpha >= beta:
            return alpha
    key = pkey(board, side, ep, castle)
    # The clock is excluded from repetition identity but included in the table
    # identity, so a score earned under a different clock is never served.
    if depth < 1:
        if in_check:
            # Repeating a position already on this line is scored as the draw
            # it would become; that is a cycle cutoff, not the threefold rule.
            if key in path or hist.get(key, 0) > 1:
                return 0
            ms = gen(board, side, ep, castle)
            if not ms:
                return -(99000 - ply)
            path = path + (key,)
            for m in sorted(
                    ms,
                    key=lambda m: -(VALUE[board[m[1]].upper()]
                                    if board[m[1]] not in '._ ' else 0) * 100
                    + VALUE[board[m[0]].upper()]):
                nb, ep2, c2 = make(board, side, ep, castle, m)
                score = -search(0, -beta, -alpha, nb, 1 - side, ep2, c2,
                                ply + 1, hist, path)
                if score > alpha:
                    alpha = score
                if alpha >= beta:
                    break
            return alpha
        stand = evaluate(board) if side == 0 else -evaluate(board)
        if stand >= beta:
            return stand
        if stand > alpha:
            alpha = stand
        for m in sorted(
                gen(board, side, ep, castle, 1),
                key=lambda m: -(VALUE[board[m[1]].upper()]
                                if board[m[1]] not in '._ ' else 0) * 100
                + VALUE[board[m[0]].upper()]):
            gain = (VALUE[board[m[1]].upper()] if board[m[1]] not in '._ '
                    else 100) + (800 if m[2] else 0)
            if stand + gain + 200 <= alpha:
                continue  # delta pruning: cannot raise alpha even if it lands
            nb, ep2, c2 = make(board, side, ep, castle, m)
            score = -search(0, -beta, -alpha, nb, 1 - side, ep2, c2,
                            ply + 1, hist, path)
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break
        return alpha
    # Threefold needs THREE occurrences: hist holds committed ones and path the
    # ones on this line, so two committed occurrences plus this node is a draw.
    # A key already on the path is cut off by the cycle heuristic instead.
    if key in path or hist.get(key, 0) > 1:
        return 0
    hit = TT.get(key + (clk,))
    tt_move = None
    if hit:
        hs = tt_load(hit[2], ply)
        if hit[0] >= depth:
            if hit[1] == 2:  # upper bound
                beta = min(beta, hs)
            else:            # exact or lower bound
                alpha = max(alpha, hs)
            if alpha >= beta:
                return hs
        tt_move = hit[3]
    # A check extends the search, but only while ply is small: past EXT_PLY
    # depth falls every move, so a checking sequence cannot run away.
    ex = in_check and ply < EXT_PLY
    # Null-move pruning: if passing still holds beta at R=2, a real move
    # does too. Skipped in check and in pawn-only endings (zugzwang).
    if depth >= 3 and not in_check and not null and beta < 90000:
        own = 'NBRQ' if side == 0 else 'nbrq'
        if any(c in key[0] for c in own):
            if -search(depth - 3, -beta, 1 - beta, board, 1 - side, 0,
                       castle, ply + 1, hist, path, 1) >= beta:
                return beta
    ms = order(board, gen(board, side, ep, castle), tt_move, ply)
    if not ms:
        return -(99000 - ply) if in_check else 0
    best = 0 if clm else -99999
    best_move = ms[0]
    flag = 2
    path = path + (key,)
    for i, m in enumerate(ms):
        nb, ep2, c2 = make(board, side, ep, castle, m)
        # Late move reductions for late, quiet, non-killer moves, with a
        # full-depth re-search when the reduced score beats alpha.
        red = (depth >= 3 and i >= 4 and not in_check
               and board[m[1]] == '.' and m != tt_move and not m[2])
        score = -search(depth - 1 - red + ex, -beta, -alpha, nb,
                        1 - side, ep2, c2, ply + 1, hist, path)
        if red and score > alpha:
            score = -search(depth - 1 + ex, -beta, -alpha, nb,
                            1 - side, ep2, c2, ply + 1, hist, path)
        if score > best:
            best = score
            best_move = m
            if score > alpha:
                alpha = score
                flag = 0
            if alpha >= beta:
                flag = 1
                if board[m[1]] == '.':
                    killers[ply] = ((m,) + tuple(
                        x for x in killers.get(ply, ()) if x != m)[:1])
                    pc = board[m[0]]
                    history[(pc, m[1])] = (history.get((pc, m[1]), 0)
                                           + depth * depth)
                break
    # A shallower search must not evict a deeper verdict for the same
    # position: the deep entry answers far more future probes than the
    # shallow one, and re-deriving it costs a full re-search. Re-read the
    # slot because a descendant search may have transposed into it.
    old = TT.get(key + (clk,))
    if not old or depth >= old[0]:
        TT[key + (clk,)] = (depth, flag, tt_store(best, ply), best_move)
    return best


def think(fen, legal, opponent, moves=()):
    """Iterative deepening over the env's legal moves under a node cap."""
    global nodes, MAX_NODES, TT, killers, history
    board, side, ep, castle = parse(fen)
    TT, killers, history = {}, {}, {}
    nodes = 0
    MAX_NODES = budget_for(opponent)
    # Committed positions with their occurrence counts: an en-passant square
    # only counts when it is playable, so history and search agree on identity.
    b, s, e, a = parse('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1')
    hist = {pkey(b, s, e, a): 1}
    for u in moves:
        b, e, a = make(b, s, e, a, (square(u[:2]), square(u[2:4]), u[4:5]))
        s = 1 - s
        k = pkey(b, s, e, a)
        hist[k] = hist.get(k, 0) + 1
    root = [((square(u[:2]), square(u[2:4]), u[4:5]), u) for u in legal]
    scores = {}
    best = root[0][1]
    for depth in range(1, 64):
        alpha = -99999
        current = None
        root.sort(key=lambda x: -scores.get(x[0], -99999))
        try:
            for m, uci in root:
                nb, ep2, c2 = make(board, side, ep, castle, m)
                score = -search(depth - 1, -99999, -alpha, nb, 1 - side,
                                ep2, c2, 1, hist, ())
                scores[m] = score
                if current is None or score > alpha:
                    alpha = score
                    current = uci
        except Budget:
            break
        best = current
        if alpha > 90000:
            break
    return best


def post(path, body):
    r = U.urlopen(U.Request(ENV + path, json.dumps(body).encode(),
                            {'content-type': 'application/json'}))
    return json.load(r)


if ENV:
    while True:
        g = post('/game', {})
        if g['status'] == 'done':
            break
        while g['status'] == 'your_move':
            move = think(g['fen'], g['legal_moves'], g['opponent_name'],
                         g['moves'])
            g = post('/move', {'game': g['game'], 'move': move})
        print(g, file=sys.stderr)   # per-game result
    print(g, file=sys.stderr)       # final record
