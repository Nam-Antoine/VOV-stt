/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // Dark mode is a class, not a media query: verification sessions run for hours and
  // the operator picks the mode, not the OS. See ThemeToggle.
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Semantic tokens. Every value is a CSS variable defined in index.css, so
        // light/dark is one place and components never name a raw palette colour.
        canvas: 'rgb(var(--canvas) / <alpha-value>)',
        surface: 'rgb(var(--surface) / <alpha-value>)',
        sunken: 'rgb(var(--sunken) / <alpha-value>)',
        line: 'rgb(var(--line) / <alpha-value>)',
        ink: 'rgb(var(--ink) / <alpha-value>)',
        muted: 'rgb(var(--muted) / <alpha-value>)',
        faint: 'rgb(var(--faint) / <alpha-value>)',
        accent: 'rgb(var(--accent) / <alpha-value>)',
        'accent-ink': 'rgb(var(--accent-ink) / <alpha-value>)',

        // Utterance states in the editor (PLAN §10).
        dirty: '#f59e0b',    // amber: edited, not yet saved
        verified: '#10b981', // green: text_verified present
      },
      fontFamily: {
        // Vietnamese diacritics need a face with good combining-mark coverage.
        transcript: ['"Noto Sans"', 'Inter', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        // The transcript's own scale — set on the container, tuned by the reader.
        utterance: ['1.0625rem', { lineHeight: '1.75' }],
      },
      maxWidth: {
        // ~75 characters of Vietnamese at the transcript size. Long lines are the
        // single biggest readability cost on a 27-second utterance.
        measure: '68ch',
      },
      keyframes: {
        'fade-in': { from: { opacity: '0' }, to: { opacity: '1' } },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        shimmer: {
          '100%': { transform: 'translateX(100%)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 150ms ease-out',
        'slide-up': 'slide-up 180ms ease-out',
        shimmer: 'shimmer 1.6s infinite',
      },
    },
  },
  plugins: [],
}
