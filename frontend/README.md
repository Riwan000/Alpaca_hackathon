# AEGIS // PRIVATE WEALTH Frontend

Frontend interface for the **Autonomous Adaptive Portfolio Hedge Agent** (Hackathon MVP).

Built with **React 18**, **TypeScript**, **Vite 6**, **TanStack React Query v5**, and **TailwindCSS 3** with the *Alabaster Spruce* design system (`#1B4332` spruce, `#A67C37` gold, `#2D6A4F` light spruce, `#1E3A8A` slate blue).

---

## Quickstart

### Prerequisites

- **Node.js 20+** and **npm**
- (Optional) Running backend API at `http://localhost:8000` (see root `README.md`)

### 1. Install Dependencies

```bash
cd frontend
npm install
```

### 2. Configure Environment

Copy the example environment configuration:

```bash
cp .env.example .env
```

| Variable | Description | Default |
|---|---|---|
| `VITE_API_BASE_URL` | Base URL of the backend API | `http://localhost:8000` |

### 3. Run Development Server

```bash
npm run dev
```

- Vite dev server starts at **`http://localhost:5173`**.
- API requests are made directly to `http://localhost:8000` (or proxied via Vite dev server).

---

## Testing & Verification

### Run Unit & Integration Tests

Runs all Vitest component tests, type assertion suites, and MSW network mock handlers:

```bash
npm test
```

### Type Check & Production Build

```bash
npm run build && npx tsc --noEmit
```

---

## Architecture & Codebase Map

```
frontend/src/
├── api/
│   ├── client.ts         # Typed fetch client with normalized ApiError handling
│   ├── queries.ts        # React Query hooks for all 7 contracts (useHedgeContext, etc.)
│   ├── types.ts          # TS interfaces & enums mirroring backend models (P1-FE-6)
│   ├── types.test-d.ts   # Contract type-level assertions & tests
│   └── index.ts          # Unified API exports
├── theme/
│   ├── ThemeContext.tsx  # Dark/light theme state & toggle provider
│   └── index.ts          # Theme tokens & palettes
├── layout/
│   ├── Layout.tsx        # Institutional brand header, navigation bar, and content shell
│   └── Layout.test.tsx   # Layout & theme toggle component tests
├── pages/
│   ├── DashboardPage.tsx       # Live portfolio vitals, strategy recommendation, agent stream
│   ├── ConfigurationPage.tsx   # Risk limits, hedge preferences & autonomy settings
│   ├── StrategyDetailsPage.tsx # Deep-dive into selected strategy & alternative hypotheses
│   └── NotFoundPage.tsx        # 404 fallback page
├── routes/
│   ├── index.tsx         # Route tree wiring Layout and Page components
│   └── routes.test.tsx   # Route navigation & MSW stub payload rendering tests (P1-FE-7)
├── providers/
│   ├── AppProviders.tsx  # Composed provider tree (QueryClient, ThemeProvider, Router)
│   └── ...
└── test/
    ├── server.ts         # MSW server & stub handlers for all 7 agent contracts
    ├── setup.ts          # Vitest test setup and cleanup lifecycle
    └── sanity.test.tsx   # Test harness sanity check (P1-FE-9)
```

---

## Phased Plan Sign-Off

This frontend implementation satisfies the Phase 1 Foundation requirements:
- **`P1-FE-6` (Git Issue #40):** Shared TS types mirroring the 7 contracts (`types.ts`, `types.test-d.ts`).
- **`P1-FE-7` (Git Issue #41):** Wired routes to stub endpoints rendering real payloads (`routes.test.tsx`, `queries.ts`).
- **`P1-FE-8` (Git Issue #42):** Dev environment config (`.env.example`) & comprehensive README.
- **`P1-FE-9` (Git Issue #43):** Vitest + RTL + MSW testing infrastructure (`setup.ts`, `server.ts`, `sanity.test.tsx`).
