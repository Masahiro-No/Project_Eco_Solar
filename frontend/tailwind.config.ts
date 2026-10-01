import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",

        canvas: '#f4f7fb',
        ink: '#0f172a',
        muted: '#64748b',
        line: '#e3e9f2',
        brand: { DEFAULT: '#1d4ed8', soft: '#eaf1ff', mid: '#3b82f6' },
        ok: { DEFAULT: '#16a34a', soft: '#e8f7ee' },
        warn: { DEFAULT: '#d97706', soft: '#fff4dc' },
        bad: { DEFAULT: '#dc2626', soft: '#fdecec' },
        sun: '#f59e0b',
      },
    },
  },
  plugins: [],
};
export default config;
