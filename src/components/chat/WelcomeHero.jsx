import React, { useState } from "react";
import {
  Package,
  Search,
  Wrench,
  ShieldCheck,
  Truck,
  ArrowRight,
  Check,
  Pencil,
} from "lucide-react";

// Production-grade empty state shown before the first user message: a centered
// brand hero, capability cards (what the assistant can do), and an inline model
// prompt — replacing the generic greeting-bubble + banner + chips stack.

// label = shown to the user; query = what's actually sent to the agent. Queries
// mirror the guided categories and are phrased so Flash routes them cleanly.
const CAPABILITIES = [
  {
    icon: Package,
    label: "Find a replacement part",
    desc: "Search by part name or PS number",
    query: "I need a replacement part",
  },
  {
    icon: Search,
    label: "Diagnose an issue",
    desc: "Describe a symptom, get likely causes",
    query: "Help me diagnose an appliance problem",
  },
  {
    icon: Wrench,
    label: "Repair instructions",
    desc: "Step-by-step guides with videos",
    query: "I need repair instructions",
  },
  {
    icon: ShieldCheck,
    label: "Check compatibility",
    desc: "Confirm a part fits your model",
    query: "Check part compatibility",
  },
];

const WelcomeHero = ({ onSelect, disabled, modelNumber, onSaveModel }) => {
  const [model, setModel] = useState("");

  const saveModel = () => {
    const trimmed = model.trim();
    if (!trimmed) return;
    onSaveModel(trimmed);
    setModel("");
  };

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col items-center px-4 py-10 text-center sm:py-14">
      {/* No brand mark in the middle — the top-left header carries the logo. */}
      <h2 className="text-[1.75rem] font-extrabold leading-tight tracking-tight text-ps-text sm:text-4xl">
        How can I help with your appliance?
      </h2>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-ps-textMuted sm:text-base">
        Your expert assistant for{" "}
        <span className="font-semibold text-ps-text">refrigerator</span> and{" "}
        <span className="font-semibold text-ps-text">dishwasher</span> parts.
        Pick a starting point or just ask.
      </p>

      {/* Capability cards — solid surfaces for a crisp, production feel */}
      <div className="mt-8 grid w-full grid-cols-1 gap-3 sm:grid-cols-2">
        {CAPABILITIES.map((cap) => {
          const Icon = cap.icon;
          return (
            <button
              key={cap.label}
              type="button"
              disabled={disabled}
              onClick={() => onSelect(cap.query)}
              className="group flex items-center gap-3.5 rounded-2xl border border-ps-border bg-ps-surface p-4 text-left shadow-card transition-all hover:-translate-y-0.5 hover:border-ps-teal/50 hover:shadow-cardHover disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-ps-tealSoft text-ps-teal transition-colors group-hover:bg-ps-teal group-hover:text-white">
                <Icon className="h-5 w-5" />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-semibold text-ps-text">
                  {cap.label}
                </span>
                <span className="mt-0.5 block text-xs leading-snug text-ps-textMuted">
                  {cap.desc}
                </span>
              </span>
              <ArrowRight className="h-4 w-4 shrink-0 text-ps-textFaint transition-all group-hover:translate-x-0.5 group-hover:text-ps-teal" />
            </button>
          );
        })}
      </div>

      {/* Secondary: track order */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => onSelect("Where is my order?")}
        className="mt-4 inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium text-ps-textMuted transition-colors hover:bg-ps-surface hover:text-ps-teal disabled:opacity-50"
      >
        <Truck className="h-4 w-4" />
        Track an existing order
      </button>

      {/* Model number prompt */}
      <div className="mt-8 w-full border-t border-ps-border/70 pt-6">
        {modelNumber ? (
          <div className="inline-flex items-center gap-2 rounded-full border border-ps-teal/25 bg-ps-teal/5 px-4 py-2 text-sm">
            <Check className="h-4 w-4 text-ps-teal" />
            <span className="text-ps-textMuted">Using model</span>
            <span className="font-mono font-semibold text-ps-text">
              {modelNumber}
            </span>
            <Pencil className="h-3.5 w-3.5 text-ps-textFaint" />
          </div>
        ) : (
          <>
            <p className="mb-2.5 text-xs font-medium text-ps-textMuted">
              Add your model number for personalized compatibility checks
              <span className="text-ps-textFaint">
                {" "}
                — optional, saved for this tab
              </span>
            </p>
            <div className="mx-auto flex max-w-sm gap-2">
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && saveModel()}
                placeholder="e.g. WRF560SEHZ00"
                className="min-w-0 flex-1 rounded-xl border border-ps-border bg-ps-elevated px-3.5 py-2.5 text-sm text-ps-text outline-none transition-colors placeholder:text-ps-textFaint focus:border-ps-teal focus:ring-1 focus:ring-ps-teal"
              />
              <button
                type="button"
                onClick={saveModel}
                className="rounded-xl bg-ps-teal px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-ps-tealDark"
              >
                Save
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default WelcomeHero;
