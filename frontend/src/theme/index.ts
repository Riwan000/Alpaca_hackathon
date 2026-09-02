/**
 * AEGIS // PRIVATE WEALTH - Design Tokens
 * Botanical Alabaster Spruce Theme Specification
 */

export const DEFAULT_BRAND_THEME = {
  name: 'AEGIS Botanical Alabaster Spruce',
  colors: {
    // Brand Accents
    primary: '#1B4332',       // Deep Imperial Spruce
    primaryHover: '#143225',
    goldBronze: '#A67C37',     // Antique Gold / Champagne Bronze
    tealTelemetry: '#0D9488',  // Streaming Realtime Data
    
    // Canvas & Surfaces (Light)
    bgMain: '#F3F7F5',         // Fresh Alabaster Botanical
    bgCard: '#FFFFFF',         // Crisp White
    bgSubtle: '#E5EDE9',       // Soft Sage Alabaster
    bgSubtleHover: '#DCE7E2',
    
    // Borders
    border: '#CCD8D2',         // 1px Technical Pine Slate
    borderDark: '#8CA397',     // High-Contrast Divider
    
    // Typography
    textMain: '#0E1713',       // Deep Pine Charcoal
    textMuted: '#52665C',      // Muted Sage
    
    // Semantic Status
    statusSafe: '#15803D',     // Protected / Optimal
    statusWarning: '#D97706',  // Drift / Volatility Spike
    statusDanger: '#BE123C',   // Risk Gate Breach / Tail Risk
    statusInfo: '#0284C7',     // Telemetry / Scheduled Cycle
  },
  darkColors: {
    bgMain: '#0B120E',
    bgCard: '#121C16',
    bgSubtle: '#18261E',
    bgSubtleHover: '#1E3026',
    border: '#23382C',
    borderDark: '#355443',
    textMain: '#E5EDE9',
    textMuted: '#8CA397',
  },
  typography: {
    serifHeading: "'Playfair Display', Georgia, serif",
    sansUI: "'Plus Jakarta Sans', system-ui, -apple-system, sans-serif",
    monoCode: "'JetBrains Mono', ui-monospace, Menlo, monospace",
  },
  borders: {
    radius: '0px', // Strict razor-sharp Swiss right-angle geometry
    hairlineTopGold: '3px solid #A67C37',
  },
} as const;

export type BrandTheme = typeof DEFAULT_BRAND_THEME;
