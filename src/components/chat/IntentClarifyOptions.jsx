import React from "react";
import { ChevronRight, Package, Wrench, CheckCircle2 } from "lucide-react";

const ICONS = {
  buy: Package,
  repair: Wrench,
  compat: CheckCircle2,
};

// Action chips when the user named a part/topic but didn't say what they want.
const IntentClarifyOptions = ({ options = [], onSelect, disabled }) => {
  if (!options.length) return null;

  return (
    <div className="mt-2 flex flex-col gap-2">
      {options.map((opt) => {
        const Icon = ICONS[opt.id] || Package;
        return (
          <button
            key={opt.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect?.(opt.message)}
            className="group flex items-center justify-between gap-3 rounded-xl border border-ps-border bg-white px-4 py-3 text-left transition-all hover:border-ps-teal/50 hover:bg-ps-tealSoft disabled:cursor-not-allowed disabled:opacity-50"
          >
            <div className="flex min-w-0 items-start gap-3">
              <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ps-tealSoft text-ps-teal">
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-ps-text">{opt.label}</p>
                {opt.description && (
                  <p className="mt-0.5 text-xs text-ps-textMuted">
                    {opt.description}
                  </p>
                )}
              </div>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-ps-textFaint transition-transform group-hover:translate-x-0.5 group-hover:text-ps-teal" />
          </button>
        );
      })}
    </div>
  );
};

export default IntentClarifyOptions;
