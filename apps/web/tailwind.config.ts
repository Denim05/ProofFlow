import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#f0f4f8",
          100: "#d9e2ec",
          200: "#bcccdc",
          300: "#9fb3c8",
          400: "#627d98",
          500: "#334e68",
          600: "#243b53",
          700: "#1e293b",
          800: "#0f172a",
          900: "#0b132b",
          950: "#070b19",
        },
        brand: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#64748b",
          500: "#1e293b",
          600: "#0b132b",
          700: "#080e21",
          800: "#060a18",
          900: "#040711",
          950: "#02040a",
        },
      },
    },
  },
  plugins: [],
};

export default config;
