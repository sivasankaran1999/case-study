import React from "react";
import { Wrench, Clock, Gauge, ShoppingCart } from "lucide-react";
import PartCard from "./PartCard";

// Splits a leading "Label:" off a step so we can bold it (e.g.
// "Inspection: Disconnect power…" -> ["Inspection", "Disconnect power…"]).
const splitLabel = (instruction = "") => {
  const m = instruction.match(/^([A-Z][A-Za-z0-9 /&'-]{1,28}):\s+(.*)$/);
  if (m) return { label: m[1], body: m[2] };
  return { label: null, body: instruction };
};

// Renders a troubleshooting / repair guide with ordered steps and any parts
// the repair requires. All content is driven by the API response.
const RepairGuideCard = ({ meta, steps = [], parts = [], modelNumber }) => {
  const title = meta?.title || "Repair Guide";
  const timeEstimate = meta?.time_estimate;
  const difficulty = meta?.difficulty;

  return (
    <div className="overflow-hidden rounded-2xl border border-ps-border bg-white shadow-card">
      <div className="flex items-center gap-3 border-b border-ps-border bg-gradient-to-r from-ps-tealSoft/60 to-white px-4 py-3.5">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-ps-teal/10 text-ps-teal">
          <Wrench className="h-4.5 w-4.5" />
        </span>
        <div className="min-w-0">
          <h4 className="truncate text-sm font-bold text-ps-text">{title}</h4>
          <p className="mt-0.5 flex items-center gap-3 text-xs text-ps-textMuted">
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {timeEstimate || "15–30 min"}
            </span>
            <span className="flex items-center gap-1">
              <Gauge className="h-3.5 w-3.5" />
              {difficulty || "Beginner"}
            </span>
          </p>
        </div>
      </div>

      {steps.length > 0 && (
        <ol className="px-4 py-4">
          {steps.map((step, idx) => {
            const num = step.step_number ?? idx + 1;
            const { label, body } = splitLabel(step.instruction);
            const isLast = idx === steps.length - 1;
            return (
              <li key={num} className="relative flex gap-3 pb-4 last:pb-0">
                {/* Connector line through the number badges */}
                {!isLast && (
                  <span
                    aria-hidden="true"
                    className="absolute left-[13px] top-7 h-[calc(100%-1.25rem)] w-px bg-ps-border"
                  />
                )}
                <span className="z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ps-teal text-xs font-bold text-white shadow-sm">
                  {num}
                </span>
                <p className="pt-0.5 text-sm leading-relaxed text-ps-text">
                  {label && <span className="font-semibold">{label}: </span>}
                  <span className={label ? "text-ps-textMuted" : ""}>{body}</span>
                </p>
              </li>
            );
          })}
        </ol>
      )}

      {parts.length > 0 && (
        <div className="border-t border-ps-border bg-ps-bgAlt/40 px-4 py-3">
          <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-ps-text">
            <ShoppingCart className="h-4 w-4 text-ps-teal" /> Parts you'll need
          </p>
          <div className="flex gap-3 overflow-x-auto pb-1 scrollbar-thin">
            {parts.map((part, idx) => (
              <PartCard
                key={part.part_number || idx}
                part={part}
                modelNumber={modelNumber}
                compact
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default RepairGuideCard;
