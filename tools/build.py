"""Reproducible build of the standalone artifact, with an explicit tier.

Tiers (the choice is always explicit; there is no default):

  compact    archive/f7/engine.py  -> the frozen F7 baseline. Its packed output
                                     is hash-pinned to the protected main.py.
  reference  engine.py             -> the development engine, which additionally
                                     contains F12 and does NOT fit the cap.

Steps per build, all deterministic and offline:
  1. Parse the source and drop every docstring and comment (AST-guided for
     docstrings, quote-aware for trailing comments). Formatting only.
  2. Write the stripped source to .localrun/build/<tier>_mini.py.
  3. Run the competition kit's compressor into .localrun/build/<tier>_candidate.py.
  4. Verify: UTF-8 byte count <= 4096, py_compile, and - when the tier is
     hash-pinned - that the candidate hash equals the pin.
  5. Rebuild from scratch and require a byte-identical candidate.
  6. Install main.py ONLY with --install, and only after every check passed.

Nothing outside .localrun/build/ is written unless --install is given, so an
unverified or over-cap build can never touch the protected artifact.

Usage:
    python3 tools/build.py --tier compact              # verify reproduction only
    python3 tools/build.py --tier compact --install    # ...and write main.py
    python3 tools/build.py --tier reference            # refuses: over budget

Exit: 0 = every check passed, 1 = over budget, invalid, unpinned or unstable.
"""
import argparse
import ast
import hashlib
import os
import py_compile
import subprocess
import sys

CAP = 4096
OUT = 'main.py'
BUILD = '.localrun/build'
COMPRESSOR = 'tiny-chess-01-kit/cli/makefun.mjs'

# tier -> (source path, expected artifact sha256 or None if not pinned)
TIERS = {
    'compact': ('archive/f7/engine.py',
                '97a6b39f16bfe13674dbf2145b880144e83d685e825cbe37cd349736067e9f0b'),
    'reference': ('engine.py', None),
}


def strip(src):
    """Remove docstrings and comments without touching executable code."""
    drop = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                for sub in ast.walk(node):
                    if (isinstance(sub, ast.Constant)
                            and isinstance(sub.value, str)
                            and sub.value == doc):
                        drop.update(range(sub.lineno, sub.end_lineno + 1))
    out = []
    for i, line in enumerate(src.splitlines(), 1):
        if i in drop or not line.strip() or line.strip().startswith('#'):
            continue
        quoted, cut = False, None
        for j, ch in enumerate(line):
            if ch in '"\'':
                quoted = not quoted
            elif ch == '#' and not quoted:
                cut = j
                break
        if cut is not None:
            line = line[:cut].rstrip()
        if line.strip():
            out.append(line)
    return '\n'.join(out) + '\n'


def pack(src, tag):
    """strip -> compress one candidate. Returns (mini bytes, candidate bytes)."""
    mini = strip(src).encode()
    mini_path = os.path.join(BUILD, f'{tag}_mini.py')
    cand_path = os.path.join(BUILD, f'{tag}_candidate.py')
    open(mini_path, 'wb').write(mini)
    r = subprocess.run(['node', COMPRESSOR, 'compress', mini_path,
                        '--out', cand_path], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(f"compressor failed: {r.stderr.strip() or r.stdout.strip()}")
    return mini, open(cand_path, 'rb').read()


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tier', required=True, choices=sorted(TIERS))
    ap.add_argument('--install', action='store_true',
                    help=f'write {OUT} after every check has passed')
    args = ap.parse_args()

    source, pin = TIERS[args.tier]
    os.makedirs(BUILD, exist_ok=True)
    src = open(source, encoding='utf-8').read()
    print(f"tier: {args.tier}")
    print(f"1. source {source}: {len(src.encode()):,} bytes  sha256 {sha(src.encode())}")

    mini, blob = pack(src, args.tier)
    print(f"2. stripped: {len(mini):,} bytes  sha256 {sha(mini)}")
    print(f"3. candidate: {len(blob):,} bytes  cap {CAP:,}  "
          f"headroom {CAP - len(blob):,}  sha256 {sha(blob)}")

    failures = []
    if len(blob) > CAP:
        failures.append(f"over budget by {len(blob) - CAP:,} bytes")
    try:
        py_compile.compile(os.path.join(BUILD, f'{args.tier}_candidate.py'),
                           cfile='/tmp/_build_check.pyc', doraise=True)
        print("4. syntax: OK")
    except py_compile.PyCompileError as ex:
        failures.append(f"syntax: {ex}")

    if pin:
        if sha(blob) == pin:
            print("5. pin: candidate matches the recorded artifact hash")
        else:
            failures.append(f"pin mismatch: expected {pin}, got {sha(blob)}")
    else:
        print("5. pin: tier is not hash-pinned (development source)")

    _, again = pack(src, args.tier)
    if again == blob:
        print("6. rebuild: byte-identical on a second run")
    else:
        failures.append("rebuild differs: the build is not reproducible")

    if os.path.exists(OUT):
        current = open(OUT, 'rb').read()
        same = current == blob
        print(f"7. {OUT} on disk: {len(current):,} bytes  sha256 {sha(current)}"
              f"  -> {'identical to candidate' if same else 'DIFFERS from candidate'}")

    if failures:
        for f in failures:
            print(f"   FAILED: {f}")
        print(f"   {OUT} left untouched")
        return 1

    if not args.install:
        print(f"8. dry run: all checks passed; pass --install to write {OUT}")
        return 0

    open(OUT, 'wb').write(blob)
    print(f"8. {OUT} installed: {len(blob):,} bytes  sha256 {sha(blob)}")
    print("   equivalence gate: python3 tests/test_standalone.py")
    return 0


if __name__ == '__main__':
    sys.exit(main())
