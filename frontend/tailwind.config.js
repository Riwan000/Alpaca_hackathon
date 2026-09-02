/** @type {import('tailwindcss').Config} */
export default {
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
        },
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
