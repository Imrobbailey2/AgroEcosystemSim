# AgroEcosystemSim: Florida Agroecosystem Farm Simulator

[![CI](https://github.com/Imrobbailey2/AgroEcosystemSim/actions/workflows/ci.yml/badge.svg)](https://github.com/Imrobbailey2/AgroEcosystemSim/actions/workflows/ci.yml)
[![Pages](https://github.com/Imrobbailey2/AgroEcosystemSim/actions/workflows/pages.yml/badge.svg)](https://imrobbailey2.github.io/AgroEcosystemSim/)

An accessible, browser-based farm management game about soils, water, crops
and money in Florida. It is packaged as SCORM 2004 3rd Edition for Canvas.

**Live build:** https://imrobbailey2.github.io/AgroEcosystemSim/

> Status: **Increment 0 (toolchain)**. The live page is a placeholder.

## First playable version (planned)

A Suwannee Valley farm with 2 fields on real SSURGO soils, growing corn over
2 game years, played 1 year per session. Players order a Mehlich-3 soil test
(rated per UF/IFAS SL129), apply lime and fertilizer, plant a cover crop, hire
custom work and sell through 1 market channel. Saving, resuming and scoring go
through Canvas. Every screen works from the keyboard.

## Repository layout

| Path | Contents |
|---|---|
| `game/` | Vite, TypeScript and Preact browser game. `src/engine/` holds UI-free simulation logic. |
| `pipeline/` | Python 3.11+ data-pack builder (`agroeco-pipeline`), tested with pytest. |
| `schemas/` | JSON Schemas shared by the game and the pipeline. |
| `scripts/` | Repository tooling, including the forbidden-data guard. |
| `.github/workflows/` | CI (lint, tests, build, accessibility) and GitHub Pages deployment. |

## Quick start

```bash
# Game (Node 24, see .nvmrc)
cd game
npm install
npm run dev          # local dev server
npm run lint && npm test && npm run build
npx playwright install chromium && npm run test:a11y

# Pipeline (Python 3.11+)
cd pipeline
python -m pip install -e ".[dev]"
pytest
```

## Data policy

UF validation data and private calibration outputs must **never** be committed.
CI fails on any path listed in [`.forbidden-paths`](.forbidden-paths). See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

Code: [MIT](LICENSE) © 2026 Rob Bailey. Data-pack values carry their own
source citations and licenses.
