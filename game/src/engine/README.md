# Simulation engine

Plain TypeScript, no UI imports. All game logic (seeded RNG, farm state,
decisions, `advance()`, soil chemistry, water balance, economics) lives here
so it can be unit-tested, replayed from a decision log, and rendered by any
map layer (top-down first, isometric later).

Rule: nothing in `src/engine/` may import from `preact` or from UI folders.

Implemented starting in Increment 3.
