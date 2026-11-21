# Dev tool: run engine.py's driver with per-move timing to correlate with
# the env's calls.ndjson. Usage: MAKEFUN_ENV_URL=... python3 tests/timed.py
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_osenv = os.environ.pop('MAKEFUN_ENV_URL', None)  # keep engine's driver idle
import engine as E
if _osenv is not None:
    os.environ['MAKEFUN_ENV_URL'] = _osenv
E.ENV = _osenv


orig_post = E.post


def post(path, body):
    t0 = time.perf_counter()
    r = orig_post(path, body)
    print(f"SENT {path} {json.dumps(body)[:60]} reply in {time.perf_counter()-t0:.2f}s "
          f"status={r['status']}", file=sys.stderr, flush=True)
    return r


E.post = post

orig_think = E.think


def think(fen, legal, opp, moves=()):
    t0 = time.perf_counter()
    mv = orig_think(fen, legal, opp, moves)
    print(f"think {opp} took {time.perf_counter()-t0:.2f}s -> {mv}",
          file=sys.stderr, flush=True)
    return mv


E.think = think

while True:
    g = post('/game', {})
    if g['status'] == 'done':
        break
    while g['status'] == 'your_move':
        mv = think(g['fen'], g['legal_moves'], g['opponent_name'], g['moves'])
        g = post('/move', {'game': g['game'], 'move': mv})
    print(g['game'], g['outcome'], g['reason'], file=sys.stderr)
print(g['wins'], g['draws'], g['losses'], file=sys.stderr)
