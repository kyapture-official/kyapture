/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        serif: ['Cormorant Garamond', 'Georgia', 'serif'],
        sans: ['Outfit', 'system-ui', 'sans-serif'],
        landing: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        cream: {
          50: '#faf7f2',
          100: '#f3ede3',
          200: '#e8ddd0',
          300: '#d4c4b0',
          400: '#c4a882',
          500: '#c17f3e',
        },
        ink: '#0f172a',
        muted: '#64748b',
        accent: '#0D9488',
        green: '#10b981',

        primary: {
          DEFAULT: '#0D9488',
          light: '#14B8A6',
          dark: '#0F766E',
        },
        charcoal: {
          DEFAULT: '#0F172A',
          light: '#1E293B',
        },
        offwhite: '#FAFAFA',
      },
      keyframes: {
        'slide-right': {
          from: { transform: 'translateX(-100%)' },
          to: { transform: 'translateX(0)' },
        },
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(16px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.95)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'slide-right': 'slide-right 0.25s ease-out',
        'fade-up': 'fade-up 0.5s ease-out both',
        'fade-in': 'fade-in 0.4s ease-out both',
        'scale-in': 'scale-in 0.2s ease-out both',
        shimmer: 'shimmer 1.5s infinite',
      },
      boxShadow: {
        'card': '0 1px 3px rgba(15, 23, 42, 0.04), 0 1px 2px rgba(15, 23, 42, 0.03)',
        'card-hover': '0 10px 30px rgba(15, 23, 42, 0.08), 0 4px 12px rgba(15, 23, 42, 0.04)',
        'sidebar': '4px 0 24px rgba(15, 23, 42, 0.04)',
        'topbar': '0 1px 12px rgba(15, 23, 42, 0.04)',
        'stat': '0 2px 12px rgba(15, 23, 42, 0.05)',
        'stat-hover': '0 8px 28px rgba(15, 23, 42, 0.1)',
        'glow-accent': '0 0 20px rgba(13, 148, 136, 0.12)',
        'glow-teal': '0 0 20px rgba(13, 148, 136, 0.15)',
      },
    },
  },
  plugins: [],
}
