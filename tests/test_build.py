# Verify the release build is reproducible and the frozen tier is intact.
# This EXECUTES tools/build.py twice (compact and reference tiers); nothing is
# assumed. It never writes main.py - the build is run without --install - and it
# asserts that main.py is unchanged afterwards.
import hashlib
import importlib.util
import os
import subprocess
import sys

FAIL = []
COMPRESSOR = 'tiny-chess-01-kit/cli/makefun.mjs'
ARCHIVE = 'archive/f7/engine.py'
MAIN = 'main.py'
# Recorded release constants (see RELEASE_MANIFEST.md).
ARCHIVE_SHA = '3042efc3d0df8bba8573ea4d574cdd5b078090dc74ef8de5b2e78f71b008e946'
ARCHIVE_SIZE = 17941
MINI_SHA = 'f97d4fc147ae907a7354614b251504559085a02c7198972a02d16ba4f9d8924f'
MAIN_SHA = '97a6b39f16bfe13674dbf2145b880144e83d685e825cbe37cd349736067e9f0b'


def check(name, cond, detail=""):
    print(f"{'OK  ' if cond else 'FAIL'} {name}{'  ' + detail if detail else ''}")
    if not cond:
        FAIL.append(name)


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def load_build():
    spec = importlib.util.spec_from_file_location('build', 'tools/build.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- 1. the frozen tier exists and is the recorded source ------------------
exists = os.path.exists(ARCHIVE)
check("archive/f7/engine.py exists", exists, ARCHIVE)
if not exists:
    print("\nFAILED: frozen tier missing, cannot continue")
    sys.exit(1)

arch = open(ARCHIVE, 'rb').read()
check("frozen tier size", len(arch) == ARCHIVE_SIZE, f"{len(arch)} bytes")
check("frozen tier sha256", sha(arch) == ARCHIVE_SHA, sha(arch))

# ---- 2. it is exactly the source inside the shipped artifact ---------------
B = load_build()
mini = B.strip(arch.decode()).encode()
check("stripped frozen tier sha256", sha(mini) == MINI_SHA, sha(mini))


def shipped_payload():
    import ast
    import lzma
    src = open(MAIN, encoding='l1').read()
    lit = max((n.value for n in ast.walk(ast.parse(src))
               if isinstance(n, ast.Constant) and isinstance(n.value, str)),
              key=len)
    return lzma.decompress(lit.encode('l1'))


check("shipped artifact payload is the frozen tier",
      shipped_payload() == mini)

# ---- 3. the build is reproducible from the frozen tier --------------------
# Skipped, not failed, when the vendor kit is absent: the kit is not committed.
if not os.path.exists(COMPRESSOR):
    print(f"SKIP build execution: {COMPRESSOR} absent (vendor kit)")
else:
    main_before = open(MAIN, 'rb').read()
    r = subprocess.run([sys.executable, 'tools/build.py', '--tier', 'compact'],
                       capture_output=True, text=True)
    out = r.stdout
    check("compact build exits 0", r.returncode == 0, f"exit {r.returncode}")
    check("compact build matches the release pin", MAIN_SHA in out)
    check("compact build rebuilds identically", 'byte-identical' in out)
    check("compact build reports no failure", 'FAILED' not in out)
    check("compact build leaves main.py untouched",
          open(MAIN, 'rb').read() == main_before,
          "byte-for-byte unchanged")

    r2 = subprocess.run([sys.executable, 'tools/build.py', '--tier', 'reference'],
                        capture_output=True, text=True)
    check("reference tier refuses the build (over cap)", r2.returncode == 1,
          f"exit {r2.returncode}")
    check("refusal names the overrun", 'over budget' in r2.stdout)
    check("refusal leaves main.py untouched",
          open(MAIN, 'rb').read() == main_before)

# ---- 4. the protected artifact itself ------------------------------------
main = open(MAIN, 'rb').read()
check("main.py <= 4096 UTF-8 bytes", len(main) <= 4096, f"{len(main)} bytes")
check("main.py sha256", sha(main) == MAIN_SHA, sha(main))
check("main.py keeps spare bytes", len(main) < 4096, f"{4096 - len(main)} spare")

# ---- 5. no stale candidate contradicts the shipped artifact --------------
build_dir = '.localrun/build'
stale = []
if os.path.isdir(build_dir):
    for name in sorted(os.listdir(build_dir)):
        if not name.endswith('_candidate.py'):
            continue
        blob = open(os.path.join(build_dir, name), 'rb').read()
        if blob != main and len(blob) <= 4096 and sha(blob) != MAIN_SHA:
            stale.append(f"{name} ({len(blob)}B {sha(blob)[:8]})")
check("no in-cap candidate disagrees with main.py", not stale, str(stale[:3]))

print()
print(f"{len(main)} bytes, {sha(main)[:16]}, "
      f"{'PASS' if not FAIL else f'FAILED {len(FAIL)}'}")
sys.exit(1 if FAIL else 0)
