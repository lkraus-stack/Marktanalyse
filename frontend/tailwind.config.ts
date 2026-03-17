import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          primary: "#0a0a14",
          card: "#12121e",
          cardHover: "#1a1a2e",
          border: "#1e1e3a",
        },
        text: {
          primary: "#e2e8f0",
          secondary: "#94a3b8",
          muted: "#64748b",
        },
        accent: {
          green: "#22c55e",
          red: "#ef4444",
          blue: "#3b82f6",
          amber: "#f59e0b",
        },
        chart: {
          bullish: "#22c55e",
          bearish: "#ef4444",
          volume: "#3b82f620",
        },
      },
    },
  },
};

export default config;
