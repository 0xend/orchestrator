import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        surface: "rgba(255, 255, 255, 0.82)",
        "surface-strong": "rgba(255, 255, 255, 0.95)",
        ink: "#1a2530",
        "ink-secondary": "#37474f",
        muted: "#4e5d69",
        faint: "#8a9aa5",
        accent: "#1f6f78",
        "accent-hover": "#185c63",
        "accent-2": "#dd6b4d",
        "accent-2-hover": "#c45a3e",
        border: "rgba(31, 111, 120, 0.25)",
      },
      fontFamily: {
        sans: ["Avenir Next", "Gill Sans", "Trebuchet MS", "Segoe UI", "sans-serif"],
        mono: ["SF Mono", "Fira Code", "JetBrains Mono", "Consolas", "monospace"],
      },
      borderRadius: {
        sm: "6px",
        md: "10px",
        lg: "16px",
        xl: "20px",
      },
    },
  },
  plugins: [],
};

export default config;
