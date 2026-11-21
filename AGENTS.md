# TINY CHESS LAB — ENGINEERING RULES

## Mission
Build an original, deterministic, compact Python chess engine
as an independent educational engineering project.

## Hard constraints
- Python 3.13 target.
- main.py must remain at or below 4096 UTF-8 bytes.
- Standard library only.
- No network access.
- No runtime LLM calls.
- No external packages in the engine.
- Deterministic move selection.
- Complete legal chess movement.

## Architecture
1. Compact board representation.
2. FEN parsing.
3. Attack detection.
4. Legal move generation.
5. Check, checkmate and stalemate.
6. Castling and en passant.
7. Promotion.
8. Negamax search.
9. Alpha-beta pruning.
10. Move ordering.
11. Material and positional evaluation.
12. Iterative deepening.

## Quality requirements
- Correctness before playing strength.
- Never silently accept illegal moves.
- Preserve castling and en passant state.
- Test every special move.
- Keep development tests outside main.py.
- Measure source size after every modification.
- Never sacrifice correctness merely to save bytes.

## Validation
- Initial position: 20 legal moves.
- Perft depth 2: 400 nodes.
- Perft depth 3: 8902 nodes.
- Add regression tests for every discovered bug.
- Record search depth, node count and elapsed time.
- Keep experiments reproducible.

## Workflow
Work in small verified milestones.
Do not rewrite the entire engine without justification.
Run tests after every meaningful change.
Inspect diffs before accepting changes.
Report failures honestly.
