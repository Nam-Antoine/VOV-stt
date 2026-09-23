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
        'accent-strong': 'rgb(var(--accent-strong) / <alpha-value>)',

        // Utterance states in the editor (PLAN §10).
        dirty: '#c98a1b',    // ochre: edited, not yet saved
        verified: '#4f7a3a', // moss: text_verified present
      },
      fontFamily: {
        // One face everywhere: Be Vietnam Pro was drawn for Vietnamese (stacked
        // diacritics: Ộ, Ữ, Ặ) and has the geometric feel of the reference design.
        sans: ['"Be Vietnam Pro"', '"Noto Sans"', 'system-ui', 'sans-serif'],
        reading: ['"Be Vietnam Pro"', '"Noto Sans"', 'system-ui', 'sans-serif'],
        transcript: ['"Be Vietnam Pro"', '"Noto Sans"', 'system-ui', 'sans-serif'],
      },
      fontSize: {
        // The transcript's own scale — set on the container, tuned by the reader.
        // The engine emits UPPERCASE only; caps need more leading and a touch of
        // tracking to stay readable over a 14-minute episode.
        utterance: ['1.0625rem', { lineHeight: '1.85', letterSpacing: '0.015em' }],
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
