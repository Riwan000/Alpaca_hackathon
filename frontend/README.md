# AEGIS // PRIVATE WEALTH Frontend

Frontend interface for the **Autonomous Adaptive Portfolio Hedge Agent** hackathon application.

## Tech Stack

- **Framework:** React 18 + TypeScript + Vite 6
- **State & Data Fetching:** TanStack React Query v5
- **Routing:** React Router v6
- **Styling:** TailwindCSS 3 + PostCSS + CSS Variables
- **Design Theme:** Alabaster Spruce (FT Luxury Editorial typography pairing, 0px razor-sharp borders, `#1B4332` spruce, `#A67C37` gold)
- **Testing:** Vitest + React Testing Library + Mock Service Worker (MSW)

## Getting Started

### 1. Install Dependencies

```bash
npm install
```

### 2. Development Server

```bash
npm run dev
```

The app will be accessible at `http://localhost:5173`. API calls to `/api` are automatically proxied to the backend at `http://localhost:8000`.

### 3. Run Tests

```bash
npm test
```

### 4. Production Build

```bash
npm run build
```

## Structure

- `src/api/` - Typed API client, fetch wrapper, and normalized `ApiError` handling
- `src/theme/` - AEGIS design tokens and `ThemeProvider` context (`data-theme` switching)
- `src/layout/` - Institutional header, masthead, nav, and content slot
- `src/pages/` - Route page shells (`DashboardPage`, `ConfigurationPage`, `StrategyDetailsPage`, `NotFoundPage`)
- `src/routes/` - Route definitions and navigation tests
- `src/providers/` - Composed provider tree (`QueryClientProvider`, `ThemeProvider`, `BrowserRouter`)
- `src/test/` - Vitest and MSW test fixtures
