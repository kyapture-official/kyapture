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
        // Warm neutrals — dashboard cards, wells, borders
        cream: {
          50: '#faf7f2',
          100: '#f3ede3',
          200: '#e8ddd0',
          300: '#d4c4b0',
          400: '#c4a882',
          500: '#c17f3e',
        },
        // Semantic surfaces (layered light -> dark: cards sit on cream-bg, sidebar is parchment)
        'cream-bg': '#f7f2e8',      // main content wrapper / page background
        'surface-light': '#fffdf8', // cards, modals, dropdowns
        parchment: '#f0e9db',       // sidebar / rail

        // Brand greens — primary actions, active nav, focus rings
        'brand-green': {
          50: '#f3f7f3',
          100: '#e3ede5',
          200: '#c7dbc9',
          300: '#9fc1a7',
          400: '#6f9c7b',
          500: '#4c7d5e', // white text: 4.8:1
          600: '#3a644b', // primary bg / link text: 6.8:1
          700: '#2e513d', // hover
          800: '#254233', // active
          900: '#1b3126',
        },

        ink: '#1a1f1b',   // deep charcoal w/ forest cast — 15:1 on cream-bg
        muted: '#5b6157', // secondary text — 5.7:1 on cream-bg
        accent: '#3a644b',

        primary: {
          DEFAULT: '#3a644b',
          light: '#4c7d5e',
          dark: '#2e513d',
        },
        charcoal: {
          DEFAULT: '#1a1f1b',
          light: '#2a312b',
        },
        offwhite: '#faf7f2',
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
        'card': '0 1px 3px rgba(26, 31, 27, 0.05), 0 1px 2px rgba(26, 31, 27, 0.03)',
        'card-hover': '0 10px 30px rgba(26, 31, 27, 0.09), 0 4px 12px rgba(26, 31, 27, 0.04)',
        'sidebar': '4px 0 24px rgba(26, 31, 27, 0.05)',
        'topbar': '0 1px 12px rgba(26, 31, 27, 0.05)',
        'stat': '0 2px 12px rgba(26, 31, 27, 0.06)',
        'stat-hover': '0 8px 28px rgba(26, 31, 27, 0.11)',
        'glow-brand': '0 0 20px rgba(58, 100, 75, 0.15)',
      },
    },
  },
  plugins: [],
}
