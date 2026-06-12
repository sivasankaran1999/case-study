import React from "react";
import { LOGO_SRC } from "../styles/theme";

const SIZES = {
  sm: "h-10",
  md: "h-12",
  lg: "h-14",
  xl: "h-16",
};

// The official PartSelect logo (house + "PartSelect" wordmark + tagline banner)
// is a transparent PNG, so it sits directly on the light UI. On green bands
// pass `onDark` to frame it in a white chip for legibility. A small "AI" pill
// marks the assistant.
const Logo = ({ size = "md", onDark = false, showAI = true }) => {
  const img = (
    <img
      src={LOGO_SRC}
      alt="PartSelect"
      className={`${SIZES[size]} w-auto object-contain`}
    />
  );

  return (
    <div className="flex items-center gap-2">
      {onDark ? (
        <span className="flex items-center rounded-lg bg-white p-1.5 shadow-sm ring-1 ring-black/5">
          {img}
        </span>
      ) : (
        img
      )}
      {showAI && (
        <span className="rounded-md bg-ps-tealSoft px-1.5 py-0.5 text-xs font-extrabold uppercase tracking-wide text-ps-teal">
          AI
        </span>
      )}
    </div>
  );
};

export default Logo;
