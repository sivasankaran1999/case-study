/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        ps: {
          // Light, e-commerce-grade surfaces (PartSelect.com feel)
          bg: "#FFFFFF", // page base
          bgAlt: "#F3F7F6", // alternating sections (faint green-grey)
          surface: "#FFFFFF", // cards
          surfaceHover: "#F3F7F6",
          elevated: "#F8FAFA", // inputs
          border: "#E3E8E7", // hairline borders
          borderStrong: "#CDD5D4",

          // Brand green (PartSelect primary)
          teal: "#337778",
          tealDark: "#285E5F", // hover
          tealDeep: "#1F4B4C", // deep bands / footer
          tealDeeper: "#16383A",
          tealSoft: "#E7F1F0", // tinted chips / icon backers
          tealGlow: "rgba(51,119,120,0.10)",

          // Brand gold/yellow (PartSelect secondary accent + CTAs)
          gold: "#F2B135",
          goldDark: "#E09E22",
          goldSoft: "#FCEFD2",

          // Text
          text: "#1A1A1A", // headings / primary
          textMuted: "#586169", // body
          textFaint: "#8A9299", // captions

          // Status
          success: "#16A34A",
          error: "#DC2626",
          warning: "#D97706",
          warningBg: "#FEF6E6",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(16,24,40,0.05), 0 1px 3px rgba(16,24,40,0.08)",
        cardHover: "0 12px 28px -10px rgba(16,24,40,0.18)",
        glow: "0 8px 20px -8px rgba(51,119,120,0.45)",
        goldGlow: "0 8px 20px -8px rgba(242,177,53,0.5)",
      },
      backgroundImage: {
        "grid-faint":
          "linear-gradient(to right, rgba(51,119,120,0.05) 1px, transparent 1px), linear-gradient(to bottom, rgba(51,119,120,0.05) 1px, transparent 1px)",
      },
      keyframes: {
        fadeInUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        bounceDot: {
          "0%, 80%, 100%": { transform: "translateY(0)", opacity: "0.35" },
          "40%": { transform: "translateY(-5px)", opacity: "1" },
        },
        pulseDot: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.5", transform: "scale(0.85)" },
        },
        // Gentle, Gemini-style drift for the aurora background blobs.
        auroraDrift: {
          "0%, 100%": { transform: "translate(0px, 0px) scale(1)" },
          "50%": { transform: "translate(24px, -18px) scale(1.08)" },
        },
        auroraDriftSlow: {
          "0%, 100%": { transform: "translate(0px, 0px) scale(1)" },
          "50%": { transform: "translate(-28px, 22px) scale(1.1)" },
        },
        // Infinite horizontal logo marquee. The track holds the list twice, so
        // translating exactly -50% loops seamlessly.
        marquee: {
          "0%": { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
      animation: {
        fadeInUp: "fadeInUp 0.35s ease-out",
        bounceDot: "bounceDot 1.2s infinite ease-in-out",
        pulseDot: "pulseDot 2s infinite ease-in-out",
        auroraDrift: "auroraDrift 16s ease-in-out infinite",
        auroraDriftSlow: "auroraDriftSlow 22s ease-in-out infinite",
        marquee: "marquee 30s linear infinite",
      },
    },
  },
  plugins: [],
};
