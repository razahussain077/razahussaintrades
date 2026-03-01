import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'brand-green': '#10b981',
        'brand-red': '#ef4444',
        'brand-yellow': '#f59e0b',
        'brand-blue': '#3b82f6',
      },
    },
  },
  plugins: [],
}
export default config
