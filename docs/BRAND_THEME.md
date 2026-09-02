# AEGIS Brand Theme & Design System Specification
## Autonomous Adaptive Portfolio Hedge Agent — Alpaca Hackathon 2026

---

## 1. Executive Summary & Brand Identity

| Property | Selected Value |
|---|---|
| **Product Brand Name** | **`AEGIS // PRIVATE WEALTH`** (or **`AEGIS BOTANICAL`**) |
| **Subtitle & Tagline** | *Autonomous Adaptive Portfolio Hedge Agent — Closed-Loop Risk Management* |
| **Theme Identity** | **Alabaster Spruce (Light Botanical)** |
| **Typography Suite** | **FT Luxury Editorial** (`Playfair Display` + `Plus Jakarta Sans` + `JetBrains Mono`) |
| **Corner Geometry** | **Sharp Right-Angle Corners (`0px` / Razor-Sharp Swiss Precision)** |
| **Elevation & Borders** | Thin 1px technical borders (`#CCD8D2`), gold top hairline rules (`#A67C37`), crisp tabular cards |

### Brand Philosophy & Tone of Voice
- **Deterministic Math & Institutional Rigor:** Every hedging decision is rooted in exact quantitative calculus (Black-Scholes, Greek sensitivities, Value-at-Risk, and max drawdown limits) rather than opaque heuristics.
- **Continuous Adaptive Protection:** Closed-loop stateful orchestration via LangGraph, dynamically rebalancing options structures when market regimes or volatility shifts.
- **Bespoke Swiss Private Banking Elegance:** High-contrast serif headings, fresh alabaster surfaces, deep evergreen accents, and razor-sharp rectangular borders reminiscent of *Financial Times* executive dossiers and Swiss private banking portals.

---

## 2. Color Palette & Semantic Design Tokens

### Canvas & Surface Tokens

| Token Name | CSS Variable | Hex Code | Purpose / Usage |
|---|---|---|---|
| **Canvas Background** | `--bg-main` | `#F3F7F5` | Fresh Alabaster Botanical canvas background |
| **Card Surface** | `--bg-card` | `#FFFFFF` | Crisp pure white card surfaces and container tiles |
| **Subtle Surface** | `--bg-subtle` | `#E5EDE9` | Soft Sage Alabaster for hover states, tables, inputs |
| **Subtle Hover** | `--bg-subtle-hover` | `#DCE7E2` | Active table row hover, selected pills |
| **Technical Border** | `--border-color` | `#CCD8D2` | 1px technical pine slate border lines |
| **Border Dark** | `--border-dark` | `#8CA397` | High-contrast divider rules and active frame borders |

### Brand Accent Tokens

| Token Name | CSS Variable | Hex Code | Purpose / Usage |
|---|---|---|---|
| **Spruce Primary** | `--brand-spruce` | `#1B4332` | Deep Imperial Spruce Green; primary CTA buttons, active tabs, hedged payoff curves |
| **Spruce Hover** | `--brand-spruce-hover` | `#143225` | Button hover states, active pressed states |
| **Antique Gold** | `--brand-gold` | `#A67C37` | Champagne Bronze / Antique Gold; hairline top borders, selected strategy badges, credit highlights |
| **Streaming Teal** | `--brand-teal` | `#0D9488` | Real-time market telemetry, WebSocket stream indicators, Delta ($\Delta$) metrics |

### Text & Semantic Alert Tokens

| Token Name | CSS Variable | Hex Code | Purpose / Usage |
|---|---|---|---|
| **Text Main** | `--text-main` | `#0E1713` | Deep Pine Charcoal; high-contrast headings, primary numbers, tabular values |
| **Text Muted** | `--text-muted` | `#52665C` | Muted Sage; secondary labels, parameters, timestamps |
| **Status Safe** | `--status-safe` | `#15803D` | Forest Green; protected floor, target hedge matched, budget checks passed |
| **Status Warning** | `--status-warning` | `#D97706` | Warm Amber; hedge drift detected, volatility spike, reassessment required |
| **Status Danger** | `--status-danger` | `#BE123C` | Ruby Crimson; tail-risk breach, budget constraint exceeded, hard risk gate block |
| **Status Info** | `--status-info` | `#0284C7` | Sky Marine; scheduled cycle triggers, general notifications |

---

## 3. Typography System & Font Pairing Rules

The design system implements **FT Luxury Editorial**, combining serif authority with modern sans legibility and non-jittering tabular monospace numbers:

### Font Hierarchy

```css
/* 1. Hero, Page Titles & Section Headings */
h1, h2, h3, .font-serif-heading {
  font-family: 'Playfair Display', Georgia, serif;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #0E1713;
}

/* 2. UI Navigation, Body Text, Buttons & Form Labels */
body, button, p, label, .font-ui {
  font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif;
  font-weight: 400; /* Regular */
  color: #0E1713;
}

/* 3. Financial Data, Greeks, Option Tickers & Timestamps */
.font-mono-code, table, .metric-figure {
  font-family: 'JetBrains Mono', ui-monospace, Menlo, monospace;
  font-feature-settings: "tnum" 1, "zero" 1; /* Tabular numbers prevent jitter */
}
```

### Typography Scale

| Element | Font Family | Size | Weight | Line Height |
|---|---|---|---|---|
| **Display Title (H1)** | `Playfair Display` | `24px` / `1.5rem` | Bold (700) | `1.2` |
| **Section Title (H2)** | `Playfair Display` | `18px` / `1.125rem` | Bold (700) | `1.3` |
| **Card Subtitle (H3)** | `Playfair Display` | `16px` / `1.0rem` | Semi-Bold (600) | `1.4` |
| **KPI Metric Figure** | `JetBrains Mono` | `24px` / `1.5rem` | Bold (700) | `1.1` |
| **Standard Body Text** | `Plus Jakarta Sans` | `13px` / `0.8125rem` | Regular (400) | `1.5` |
| **Greeks & Ticker Cells** | `JetBrains Mono` | `12px` / `0.75rem` | Bold (700) | `1.2` |
| **Micro Labels & Badges** | `JetBrains Mono` | `10px` / `0.625rem` | Bold (700) | `1.0` |

---

## 4. Box Geometry, Borders & Elevation

- **Corner Radius:** Strict **`0px` (Razor-Sharp)** right-angle geometry across all cards, KPI tiles, buttons, tabs, input fields, badges, and payoff frames.
- **Border Rules:** 1px solid `#CCD8D2` on all standard cards.
- **Gold Top Hairline Accent:** High-priority cards (Recommendation Hero, Masthead, Alpaca Order Slip) feature a **3px solid `#A67C37` top hairline accent**.
- **Hero Frame Outline:** 2px solid `#1B4332` for the active recommended strategy container.
- **Shadows:** Minimal, subtle institutional elevation: `box-shadow: 0 1px 3px 0 rgba(27, 67, 50, 0.04);`.

---

## 5. Architectural Layouts & UI Blueprints

### Layout 1: The 3-Column Institutional Terminal *(Asymmetrical Wall Street Grid)*
- **Left Column (25%) — Portfolio Vitals & Drift Meter:**
  - Total Equity Exposure (AUM: $\$250,000.00$).
  - Available Cash Reserve & Cash Drag ($0.11\%$).
  - Market Beta ($\beta = 1.12$) and $95\%$ 1-Day Value at Risk ($\text{VaR} = -2.65\%$).
  - **Hedge Drift Meter:** Visual horizontal gauge tracking current protection ($85.0\%$) against target threshold.
- **Center Column (50%) — Strategy Decision Room:**
  - **Recommendation Hero:** Selected Collar (`SPY 540P / 565C`), Net Premium ($-\$280$ Credit), and Multi-Greek HUD ($\Delta, \Gamma, \Theta, \nu$).
  - **Payoff Profile Curve:** High-precision SVG diagram with solid Deep Spruce (`#1B4332`) floor and shaded safe-harbor fill (`rgba(45, 106, 79, 0.18)`).
- **Right Column (25%) — Streaming Agent Activity & Alpaca Trail:**
  - Real-time timestamped event log showing LangGraph node execution and Alpaca paper order status.

---

### Layout 2: Quantitative Scenario & Stress-Testing Sandbox
- **Interactive Market Shock Slider:** Real-time stress testing from $-20\%$ (crash) to $+10\%$ (rally).
- **Live Capital Preserved Calculation:** Immediate mathematical readout comparing unhedged loss against hedged capped floor.
- **Contract Leg Status Matrix:** In-the-money put exercise value vs. expired short call premium retention.

---

### Layout 3: The Multi-Agent Council & Explainability Audit
- Comprehensive consensus cards for all 6 specialized agents:
  1. **Market Agent:** Volatility regime detection and IV percentile evaluation.
  2. **Options Agent:** Strike chain retrieval and Black-Scholes Greek calculation.
  3. **Strategy Manager:** Multi-hypothesis ranking (Collar vs. Put Spread vs. Outright Put).
  4. **Risk Gate:** Margin sufficiency, spread liquidity, and slippage guard verification.
  5. **Execution Agent:** Alpaca MCP multi-leg order routing.
  6. **Monitoring Agent:** Continuous delta tracking and auto-roll rule watch.

---

### Layout 4: Alpaca Multi-Leg Order Ticket & Execution Slip
- Institutional trade confirmation slip detailing:
  - Leg 1: Buy to Open 2x `SPY260918P00540000` @ $\$4.20$ ($\$840$ debit).
  - Leg 2: Sell to Open 2x `SPY260918C00565000` @ $\$4.90$ ($\$980$ credit).
  - Net Transaction: $+\$140.00$ cash received.

---

## 6. Frontend Code Integration

### Tailwind CSS Configuration (`frontend/tailwind.config.js`)

```javascript
/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      borderRadius: {
        DEFAULT: '0px',
        none: '0px',
        sm: '0px',
        md: '0px',
        lg: '0px',
        xl: '0px',
        '2xl': '0px',
      },
      colors: {
        brand: {
          spruce: '#1B4332',
          spruceHover: '#143225',
          gold: '#A67C37',
          teal: '#0D9488',
        },
        surface: {
          alabaster: '#F3F7F5',
          card: '#FFFFFF',
          subtle: '#E5EDE9',
          subtleHover: '#DCE7E2',
        },
        border: {
          DEFAULT: '#CCD8D2',
          dark: '#8CA397',
        },
        pine: {
          DEFAULT: '#0E1713',
          muted: '#52665C',
        },
        status: {
          safe: '#15803D',
          warning: '#D97706',
          danger: '#BE123C',
          info: '#0284C7',
        }
      },
      fontFamily: {
        display: ['"Playfair Display"', 'Georgia', 'serif'],
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};
```

### TypeScript Design Tokens (`frontend/src/theme/index.ts`)

Import ready-to-use tokens into any React component:

```typescript
import { DEFAULT_BRAND_THEME } from '@/theme';

const primaryColor = DEFAULT_BRAND_THEME.colors.primary; // #1B4332
const goldAccent = DEFAULT_BRAND_THEME.colors.goldBronze; // #A67C37
const bgMain = DEFAULT_BRAND_THEME.colors.bgMain; // #F3F7F5
```

---

## 7. Interactive Prototypes & Live Artifacts

- **Overall Design Explorer (4 Layouts):** [overall_design_concepts.html](file:///C:/Users/LEGION/.gemini/antigravity/brain/3bd044a3-ee35-4dd9-b6b1-00dfd2b1e8a0/overall_design_concepts.html)
- **Sharp Alabaster Showcase:** [alabaster_spruce_showcase.html](file:///C:/Users/LEGION/.gemini/antigravity/brain/3bd044a3-ee35-4dd9-b6b1-00dfd2b1e8a0/alabaster_spruce_showcase.html)
- **Theme Definition Source:** [frontend/src/theme/index.ts](file:///c:/Users/LEGION/Desktop/Projects/Alpaca_hackathon/frontend/src/theme/index.ts)
