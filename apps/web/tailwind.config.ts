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
        obsidian: {
          950: "#030712",
          900: "#050b18",
          850: "#081026",
          800: "#0c1838",
          750: "#0f2048",
          700: "#132759",
          600: "#1e3a78",
          500: "#2d529f",
        },
        cyber: {
          cyan: "#00f2fe",
          blue: "#38bdf8",
          electric: "#2563eb",
          teal: "#06b6d4",
          violet: "#8b5cf6",
          purple: "#a855f7",
          amber: "#f59e0b",
          rose: "#f43f5e",
          emerald: "#10b981",
        },
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
      boxShadow: {
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.45)",
        "glass-elevated": "0 16px 48px -8px rgba(0, 0, 0, 0.6)",
        "neon-cyan": "0 0 25px -3px rgba(6, 182, 212, 0.45)",
        "neon-violet": "0 0 25px -3px rgba(139, 92, 246, 0.45)",
        "neon-amber": "0 0 25px -3px rgba(245, 158, 11, 0.45)",
        "neon-emerald": "0 0 25px -3px rgba(16, 185, 129, 0.45)",
      },
      animation: {
        "pulse-slow": "pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        float: "float 6s ease-in-out infinite",
        "laser-scan": "laserScan 3s ease-in-out infinite alternate",
      },
      keyframes: {
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-6px)" },
        },
        laserScan: {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
