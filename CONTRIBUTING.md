# Contributing

Thanks for helping build the Florida Agroecosystem Farm Simulator.

## Workflow

1. Create a branch from `main` (`inc<N>-short-name` for plan increments,
   `fix-short-name` for fixes).
2. Keep each pull request to one increment or one fix.
3. CI must pass (data guard, lint, tests, build, accessibility) before merge.
4. Merges to `main` deploy to GitHub Pages automatically.

## Local setup

- **Game:** Node 24 (`.nvmrc`). Run `cd game && npm install`, then
  `npm run dev`. Before pushing, run `npm run lint && npm test && npm run build`.
- **Pipeline:** Python 3.11 or later. Run
  `cd pipeline && python -m pip install -e ".[dev]" && pytest`.
- **Data guard:** `python scripts/check_forbidden.py`.

## Code conventions

- TypeScript strict mode. Game logic lives in `game/src/engine/` and must not
  import UI code, so it stays deterministic and replayable.
- Every interactive feature must work from the keyboard and pass axe with no
  serious or critical violations.
- Python: type hints, docstrings and `ruff` clean.

## Data rules

- **Never commit UF validation data or private DSSAT calibration output.**
  Keep it outside the repository or in a git-ignored folder such as
  `private/` or `uf-validation/`. CI fails on any path in `.forbidden-paths`.
- If such data is committed by mistake, do not just delete it in a new
  commit, because it remains in the history. Tell the maintainer so the
  history can be cleaned.
- Every value in a public data pack needs a source entry (citation, URL,
  access date, license). Data tables (CSV) are welcome from non-programmers.

## License

By contributing you agree that your contributions are licensed under the MIT
License in `LICENSE`.
