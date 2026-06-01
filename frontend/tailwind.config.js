/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        serif: ['Cormorant Garamond', 'Georgia', 'serif'],
        sans:  ['Outfit', 'system-ui', 'sans-serif'],
      },
      colors: {
        cream: {
          50:  '#faf7f2',
          100: '#f3ede3',
          200: '#e8ddd0',
          300: '#d4c4b0',
          400: '#c4a882',
          500: '#c17f3e',
        },
        ink:    '#1e1a16',
        muted:  '#9a8b7c',
        accent: '#c17f3e',
        green:  '#4a7c6f',
      },
    },
  },
  plugins: [],
}
