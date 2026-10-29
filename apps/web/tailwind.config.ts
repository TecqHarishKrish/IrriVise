import type { Config } from 'tailwindcss';

const token = (name: string) => `hsl(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    container: { center: true, padding: '1rem' },
    extend: {
      colors: {
        border: token('border'),
        input: token('input'),
        ring: token('ring'),
        background: token('background'),
        foreground: token('foreground'),
        brand: { DEFAULT: token('brand'), foreground: token('brand-foreground') },
        primary: { DEFAULT: token('primary'), foreground: token('primary-foreground') },
        secondary: { DEFAULT: token('secondary'), foreground: token('secondary-foreground') },
        muted: { DEFAULT: token('muted'), foreground: token('muted-foreground') },
        accent: { DEFAULT: token('accent'), foreground: token('accent-foreground') },
        warning: { DEFAULT: token('warning'), foreground: token('warning-foreground'), soft: token('warning-soft') },
        destructive: { DEFAULT: token('destructive'), foreground: token('destructive-foreground'), soft: token('destructive-soft') },
        success: { DEFAULT: token('success'), soft: token('success-soft') },
        card: { DEFAULT: token('card'), foreground: token('card-foreground') },
        popover: { DEFAULT: token('popover'), foreground: token('popover-foreground') },
        sidebar: { DEFAULT: token('sidebar'), foreground: token('sidebar-foreground'), active: token('sidebar-active'), muted: token('sidebar-muted') },
      },
      borderRadius: { lg: '0.75rem', md: '0.5rem', sm: '0.375rem' },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: { card: '0 1px 2px rgb(16 40 32 / 0.04), 0 2px 8px rgb(16 40 32 / 0.04)' },
      keyframes: { 'pulse-soft': { '0%,100%': { opacity: '1' }, '50%': { opacity: '.55' } } },
      animation: { 'pulse-soft': 'pulse-soft 1.8s ease-in-out infinite' },
    },
  },
  plugins: [],
} satisfies Config;
