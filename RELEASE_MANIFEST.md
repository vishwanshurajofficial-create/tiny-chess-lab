# Release manifest

All values below were recomputed from the filesystem during the Phase 11
release audit (Python 3.13.17, Node v24.21.0) — none are copied from prior
reports.

## Protected artifacts

| File | Bytes | SHA-256 |
|---|---|---|
| `main.py` | **4,089** | `97a6b39f16bfe13674dbf2145b880144e83d685e825cbe37cd349736067e9f0b` |
| `archive/f7/engine.py` (source of `main.py`) | 17,941 | `3042efc3d0df8bba8573ea4d574cdd5b078090dc74ef8de5b2e78f71b008e946` |
| `engine.py` (reference tier) | 20,321 | `3f60ac57e2aa474bb70fe72c91d7057875516e4cef359f2bea676743a0258fdc` |
| `tools/build.py` | 6,258 | `474faa5c6205d44114d2785c9e31a5b496b22865135ee2c61d4e8c3e3c36f1c2` |
| `tests/test_build.py` (release gate) | 4,547 | `e723a33290ac53eb15931b6db99211cd1e235cac63770218ce9439127f4d2183` |

Hard cap on `main.py`: **4,096 UTF-8 bytes**. Headroom as shipped: **7 bytes**.

`main.py` is a `makefun-compress/v1` entrypoint: a two-line `#coding:l1` stub
whose payload is an LZMA-ALONE stream (properties byte `0x03`, i.e.
lc=3/lp=0/pb=0; 13-byte header; uncompressed size field 14,008). The packed
source inside it is:

| Artifact source | Bytes | SHA-256 |
|---|---|---|
| decompressed `main.py` payload | 14,008 | `f97d4fc147ae907a7354614b251504559085a02c7198972a02d16ba4f9d8924f` |

## Build

```bash
python3 tools/build.py --tier compact             # verify reproduction, writes nothing
python3 tools/build.py --tier compact --install   # rewrite main.py after all checks
python3 tools/build.py --tier reference           # expected to refuse (over cap)
```

Tier selection is mandatory; there is no default source. Steps, all
deterministic and offline: strip docstrings and comments (AST-driven) →
`makefun compress` into `.localrun/build/<tier>_candidate.py` → byte count ≤
4,096 → `py_compile` → candidate SHA-256 vs the recorded pin (pinned tiers only)
→ rebuild from scratch and require a byte-identical result → install `main.py`
only with `--install`. Nothing outside `.localrun/build/` is written otherwise.

### Source-to-artifact reproduction (verified)

| Stage | Bytes | SHA-256 |
|---|---|---|
| `archive/f7/engine.py` | 17,941 | `3042efc3d0df8bba8573ea4d574cdd5b078090dc74ef8de5b2e78f71b008e946` |
| stripped (`compact_mini.py`) | 14,008 | `f97d4fc147ae907a7354614b251504559085a02c7198972a02d16ba4f9d8924f` |
| packed candidate | **4,089** | `97a6b39f16bfe13674dbf2145b880144e83d685e825cbe37cd349736067e9f0b` |

The packed candidate is byte-identical to `main.py`, and the stripped source is
byte-identical to the payload decompressed out of `main.py` — both directions of
the correspondence are checked, in `tools/build.py` and `tests/test_build.py`
respectively.

The reference tier does not fit:

| Candidate | Bytes | SHA-256 |
|---|---|---|
| built from `engine.py` (F12) | 4,219 | `c321edf9304d11f944ff3d99ffb3765a6a2723abbb0c6730ca2c9f8dcfe4ea4b` |

Because 4,219 > 4,096 the build refuses and leaves `main.py` at the pinned
hash. That refusal is the expected, correct outcome for the current source —
it is the mechanism that protects the release, not a failure.

### Gates that were mutation-tested

| Mutation | Evidence | Result |
|---|---|---|
| Expected hash altered | candidate was correct | rejected (pin mismatch) |
| Frozen tier edited one character (`EXT_PLY 16→17`) | artifact 4,093 B, **inside** the cap | rejected by hash alone |
| Reference tier (F12) | artifact 4,219 B | rejected, over budget by 123 |

`main.py` was verified bit-for-bit unchanged after every one of these runs.

## Toolchain dependency

`tools/build.py` invokes the competition harness:

```
tiny-chess-01-kit/cli/makefun.mjs   (makefun 0.1.0, node ≥ 24)
```

The kit is vendor material and is **not** committed. The pinned archive is:

| Dependency | Bytes | SHA-256 |
|---|---|---|
| `tiny-chess-01-kit.tar.gz` | 7,977,571 | `16652036b5245557eeaa2d27f5969cd478bc7a5c645784f6010b9ff678e478fe` |

The archive was verified byte-identical in content to the extracted 24 MB
`tiny-chess-01-kit/` tree (32/32 files, no size or content mismatches), so it is
provenance rather than unique content.

Tests do not require the kit. Only rebuilding `main.py` does.

## Verification commands

```bash
shasum -a 256 main.py engine.py archive/f7/engine.py tools/build.py
wc -c main.py                      # 4089
python3 -c "import py_compile; py_compile.compile('main.py', doraise=True)"
for t in tests/dev.py tests/test_*.py; do python3 "$t" || echo "FAILED $t"; done
```

Expected: `main.py` 4,089 bytes; eleven suites pass with 502 assertions total.

## Verified state at freeze

- Two-tier split: reference (`engine.py`, F1–F7 + F12) and compact
  (`archive/f7/engine.py` → `main.py`, F1–F7 only). **Not feature-equivalent.**
- Move generation: all 20 published perft counts match, in both tiers.
- Rule probes: castling rights and rook transposition, en passant, promotion,
  checkmate, stalemate — all confirmed.
- Evaluation symmetry, quiescence, mate distance, killer bounds, extension
  termination, TT normalisation and replacement, threefold, state restoration,
  budget mapping, determinism across hash seeds — all confirmed.
- Package: standard library only; no network on import (`if ENV:` guard);
  deterministic node-limited search.
- Known gaps: F12 absent from the artifact; no dead-position detection in
  either tier; no draw-claim channel. See `LIMITATIONS.md`.

## Repository state

- Branch `master` is **unborn**: no project commit exists yet.
- 24 harness checkpoint commits exist under `refs/t3/orchestration-v2/...`;
  they are tool artefacts, not project history, are not on `master`, and the
  count grows as sessions checkpoint. They should be left alone, never
  deleted, and never published with `git push --all`.
- No remotes, no stashes, no notes.
- Working tree is entirely untracked at freeze time.
