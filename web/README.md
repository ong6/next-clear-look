# Next Clear Look web

React, strict TypeScript, Vite, CesiumJS, Zustand, MSW, Vitest, and Playwright implementation of the mission and evidence interface.

```bash
pnpm install
VITE_NCL_MOCK=1 VITE_NCL_TEST=1 pnpm --dir web dev --host 127.0.0.1 --port 5180
```

The mocked app runs at `http://localhost:5180` and serves the examples under `../contracts/examples/` through MSW. No Cesium ion token is used. NASA Blue Marble and Black Marble imagery are bundled under `public/imagery`; EOX is an optional online close-zoom layer only.

Verification:

```bash
pnpm --dir web contract:check
pnpm --dir web check
pnpm --dir web build
pnpm --dir web test:e2e
```

`VITE_NCL_TEST=1` exposes the deterministic `window.__ncl.setTime()` and `window.__ncl.pause()` hooks. The readiness hook is the `ncl:ready` window event plus `html[data-ncl-ready="true"]`.
