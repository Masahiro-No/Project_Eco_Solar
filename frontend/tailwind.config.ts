import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-noto-thai)', 'var(--font-geist-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-geist-mono)', 'ui-monospace', 'monospace'],
      },
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",

        // values live in src/app/globals.css (light and dark); <alpha-value> keeps bg-brand/90 and the like working
        canvas: 'rgb(var(--c-canvas) / <alpha-value>)',
        ink: 'rgb(var(--c-ink) / <alpha-value>)',
        muted: 'rgb(var(--c-muted) / <alpha-value>)',
        line: 'rgb(var(--c-line) / <alpha-value>)',
        brand: {
          DEFAULT: 'rgb(var(--c-brand) / <alpha-value>)',
          soft: 'rgb(var(--c-brand-soft) / <alpha-value>)',
          mid: 'rgb(var(--c-brand-mid) / <alpha-value>)',
        },
        ok: { DEFAULT: 'rgb(var(--c-ok) / <alpha-value>)', soft: 'rgb(var(--c-ok-soft) / <alpha-value>)' },
        warn: { DEFAULT: 'rgb(var(--c-warn) / <alpha-value>)', soft: 'rgb(var(--c-warn-soft) / <alpha-value>)' },
        bad: { DEFAULT: 'rgb(var(--c-bad) / <alpha-value>)', soft: 'rgb(var(--c-bad-soft) / <alpha-value>)' },
        sun: 'rgb(var(--c-sun) / <alpha-value>)',
      },
    },
  },
  plugins: [],
};
export default config;
