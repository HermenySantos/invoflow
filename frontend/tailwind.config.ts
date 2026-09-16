import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#f3f6f5',
          100: '#e2ebe7',
          200: '#c4d6ce',
          300: '#8fb3a4',
          400: '#4d7f6c',
          500: '#1B4D3E',
          600: '#1B4D3E',
          700: '#143D32',
          800: '#0f2e26',
          900: '#0b211b',
          950: '#061410',
        },
        success: {
          500: '#22c55e',
          600: '#16a34a',
        },
        warning: {
          500: '#f59e0b',
          600: '#d97706',
        },
        danger: {
          500: '#8B2E2E',
          600: '#8B2E2E',
        },
      },
      fontFamily: {
        sans: ['var(--font-plex)', 'var(--font-inter)', 'Inter', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        lg: '6px',
        xl: '6px',
      },
    },
  },
  plugins: [],
};

export default config;
