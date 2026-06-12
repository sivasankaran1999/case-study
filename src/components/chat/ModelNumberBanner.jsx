import React, { useState } from "react";
import { Lightbulb, X } from "lucide-react";

// Prompts the user to save their appliance model number for personalized
// compatibility checks. Dismissable; hidden once a model is saved.
const ModelNumberBanner = ({ onSave }) => {
  const [value, setValue] = useState("");
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return null;

  const handleSave = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSave(trimmed);
    setValue("");
  };

  return (
    <div className="rounded-xl border border-ps-teal/25 bg-ps-teal/5 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="flex items-start gap-2 text-sm font-medium text-ps-text">
          <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-ps-teal" />
          Enter your model number for personalized compatibility checks (saved
          for this tab — survives refresh until you close it)
        </p>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Dismiss"
          className="shrink-0 text-ps-textFaint transition-colors hover:text-ps-text"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleSave()}
          placeholder="Enter model number..."
          className="min-w-0 flex-1 rounded-lg border border-ps-border bg-ps-elevated px-3 py-2 text-sm text-ps-text outline-none transition-colors placeholder:text-ps-textFaint focus:border-ps-teal focus:ring-1 focus:ring-ps-teal"
        />
        <button
          type="button"
          onClick={handleSave}
          className="rounded-lg bg-ps-teal px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-ps-tealDark"
        >
          Save
        </button>
      </div>
    </div>
  );
};

export default ModelNumberBanner;
