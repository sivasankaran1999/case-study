import React from "react";
import { AVATAR_SRC } from "../../styles/theme";

// Three bouncing dots in the agent message position, shown while awaiting a
// response from the backend.
const TypingIndicator = () => {
  return (
    <div className="flex items-end gap-2.5">
      <img
        src={AVATAR_SRC}
        alt="PartSelect AI"
        className="h-10 w-10 shrink-0 rounded-full bg-white object-cover shadow-sm ring-1 ring-ps-border"
      />
      <div className="flex items-center gap-1 rounded-2xl rounded-bl-sm border border-ps-border bg-ps-bgAlt px-4 py-3">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="h-2 w-2 rounded-full bg-ps-teal animate-bounceDot"
            style={{ animationDelay: `${i * 0.16}s` }}
          />
        ))}
      </div>
    </div>
  );
};

export default TypingIndicator;
