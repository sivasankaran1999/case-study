import React from "react";
import { Package, HelpCircle, Wrench, ShieldCheck, Truck } from "lucide-react";

// label = what the user sees; query = what's actually sent to the agent.
// Queries mirror the four guided entry categories (plus order tracking) and are
// phrased so Flash routes them cleanly — no keyword router involved.
const CHIPS = [
  {
    icon: Package,
    label: "Find a replacement part",
    query: "I need a replacement part",
  },
  {
    icon: HelpCircle,
    label: "Diagnose an appliance issue",
    query: "Help me diagnose an appliance problem",
  },
  {
    icon: Wrench,
    label: "Repair instructions",
    query: "I need repair instructions",
  },
  {
    icon: ShieldCheck,
    label: "Check part compatibility",
    query: "Check part compatibility",
  },
  { icon: Truck, label: "Track my order", query: "Where is my order?" },
];

// Quick-start prompts shown only before the first user message.
const SuggestionChips = ({ onSelect, disabled }) => {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {CHIPS.map((chip) => {
        const Icon = chip.icon;
        return (
          <button
            key={chip.label}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(chip.query || chip.label)}
            className="inline-flex items-center gap-2 rounded-full border border-ps-border bg-ps-surface px-4 py-2.5 text-[15px] font-medium text-ps-text shadow-sm transition-all hover:-translate-y-0.5 hover:border-ps-teal/50 hover:bg-ps-surfaceHover hover:text-ps-teal hover:shadow-card disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Icon className="h-[18px] w-[18px] text-ps-teal" />
            {chip.label}
          </button>
        );
      })}
    </div>
  );
};

export default SuggestionChips;
