// Central design tokens for the PartSelect AI Chat Agent frontend.
// Light, e-commerce-grade theme aligned with PartSelect.com branding:
// brand green (#337778) primary + gold/yellow (#F2B135) accent.

export const colors = {
  bg: "#FFFFFF",
  bgAlt: "#F3F7F6",
  surface: "#FFFFFF",
  surfaceHover: "#F3F7F6",
  elevated: "#F8FAFA",
  border: "#E3E8E7",
  borderStrong: "#CDD5D4",

  teal: "#337778",
  tealDark: "#285E5F",
  tealDeep: "#1F4B4C",
  tealSoft: "#E7F1F0",

  gold: "#F2B135",
  goldDark: "#E09E22",
  goldSoft: "#FCEFD2",

  text: "#1A1A1A",
  textMuted: "#586169",
  textFaint: "#8A9299",

  success: "#16A34A",
  error: "#DC2626",
  warning: "#D97706",
};

export const brands = [
  "GE Appliances",
  "Whirlpool",
  "Frigidaire",
  "Samsung",
  "KitchenAid",
  "LG",
  "Maytag",
  "Kenmore",
];

export const PARTSELECT_URL = "https://www.partselect.com";
export const LOGO_SRC = "/assets/partselect-logo.svg";
export const AVATAR_SRC = "/assets/partselect-avatar.png";

const theme = { colors, brands, PARTSELECT_URL, LOGO_SRC };
export default theme;
