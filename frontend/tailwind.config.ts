import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      // Keep in sync with the CSS variables in app/globals.css (see the
      // palette-refinement note there).
      colors: {
        night: "#080D18",
        panel: "#111A2C",
        edge: "#24344E",
        body: "#E2E8F0",
        muted: "#8B9BB4",
        accent: "#22D3EE",
        critical: "#EF4444",
        high: "#F59E0B",
        medium: "#FBBF24",
        ok: "#34D399",
      },
      fontFamily: {
        sans: [
          "var(--font-inter)",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "var(--font-jetbrains)",
          "ui-monospace",
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          "monospace",
        ],
      },
    },
  },
  plugins: [],
};

export default config;
