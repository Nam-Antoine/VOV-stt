/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Utterance states in the editor (PLAN §10).
        dirty: '#f59e0b',    // amber: edited, not yet saved
        verified: '#10b981', // green: text_verified present
      },
      fontFamily: {
        // Vietnamese diacritics need a face with good combining-mark coverage.
        transcript: ['"Noto Sans"', 'Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
