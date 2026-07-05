import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#D0240F", dark: "#BB2009" },
        canvas: "#F7F7F7",
        ink: "#121212",
        brand: { DEFAULT: "#D0240F", hover: "#BB2009", active: "#A01B08", muted: "#AE453F", selected: "#FFE8DD" },
        "text-secondary": "#525252",
        "text-tertiary": "#737373",
        "border-subtle": "#DCDCDC",
        "border-default": "#C4C4C4",
        "bg-subtle": "#F0F0F0",
        "bg-surface": "#EFEFEF",
        elevated: "#FFFFFF",
        danger: "#DC2626",
      },
      boxShadow: {
        soft: "0 10px 32px rgba(18,18,18,0.08)",
        navbar: "0 10px 34px -28px rgba(18,18,18,0.46)",
      },
    },
  },
  plugins: [],
};

export default config;
