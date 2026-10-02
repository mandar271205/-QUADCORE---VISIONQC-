/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'vqc-bg': '#0f1117',
        'vqc-surface': '#1a1d27',
        'vqc-panel': '#21263a',
        'vqc-border': '#2d3348',
        'vqc-text': '#e2e8f0',
        'vqc-muted': '#8b92a5',
        'vqc-pass': '#22c55e',
        'vqc-fail': '#ef4444',
        'vqc-review': '#f59e0b',
        'vqc-accent': '#3b82f6',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
