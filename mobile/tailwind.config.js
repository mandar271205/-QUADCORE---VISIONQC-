/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
    "./components/**/*.{js,jsx,ts,tsx}",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        vqc: {
          bg: '#0F172A',
          surface: '#1E293B',
          panel: '#1E293B',
          border: '#334155',
          text: '#F8FAFC',
          muted: '#94A3B8',
          accent: '#06B6D4',
          pass: '#22C55E',
          fail: '#EF4444',
          review: '#F59E0B'
        }
      }
    },
  },
  plugins: [],
}
