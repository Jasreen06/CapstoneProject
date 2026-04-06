/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        maritime: {
          bg: '#0f172a',
          card: '#1e293b',
          border: '#334155',
        },
      },
    },
  },
  plugins: [],
};
