# SCORM round-trip spike (Increment 1)

A throwaway SCORM 2004 3rd Edition package that proves Canvas can save,
resume and score a large compressed save before the game relies on it.
It is not part of the game; the findings feed Increment 8.

| File | Purpose |
|---|---|
| `src/payload.ts` | Deterministic mock farm state → deflate-raw → base64 save string; SHA-256 checksum |
| `src/scormApi.ts` | Finds the LMS `API_1484_11`; otherwise uses a scorm-again stand-in persisted to localStorage |
| `src/main.ts`, `index.html` | Accessible test page (save 30k / 60k, verify, score, interactions, exit) |
| `scripts/package.mjs` | Writes `imsmanifest.xml` and a reproducible zip with no dependencies |
| `tests/*.test.*` | Node unit tests (payload, packager) |
| `tests/roundtrip.spec.ts` | Playwright standalone round trip, including keyboard-only use |

```bash
npm install
npm test              # unit tests
npm run build         # tsc + vite -> dist/
npm run package       # -> artifacts/agroeco-scorm-roundtrip.zip
npx playwright install chromium && npm run test:e2e
npm run dev           # standalone page in a browser
```

The manual Canvas test is in [`docs/increment-1-canvas-checklist.md`](../../docs/increment-1-canvas-checklist.md).
