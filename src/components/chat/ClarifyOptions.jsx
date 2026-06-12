import React from "react";
import { ChevronRight, CheckCircle2, ExternalLink } from "lucide-react";

const formatPrice = (price) => {
  if (price === null || price === undefined || isNaN(Number(price))) return null;
  return `$${Number(price).toFixed(2)}`;
};

const FitBadge = ({ fits, productUrl }) => {
  // Confirmed compatible with the user's model.
  if (fits === true) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-ps-success/10 px-2 py-0.5 text-[11px] font-semibold text-ps-success ring-1 ring-ps-success/20">
        <CheckCircle2 className="h-3 w-3" />
        Fits your model
      </span>
    );
  }
  // In-category but not in our (incomplete) cache — let the user confirm on
  // PartSelect instead of showing a discouraging false negative.
  if (fits === "verify") {
    if (!productUrl) return null;
    return (
      <span
        role="link"
        tabIndex={0}
        onClick={(e) => {
          e.stopPropagation();
          window.open(productUrl, "_blank", "noopener,noreferrer");
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.stopPropagation();
            window.open(productUrl, "_blank", "noopener,noreferrer");
          }
        }}
        className="inline-flex cursor-pointer items-center gap-1 rounded-full bg-ps-tealSoft px-2 py-0.5 text-[11px] font-semibold text-ps-teal ring-1 ring-ps-teal/20 hover:bg-ps-teal/10"
      >
        Verify fit on PartSelect
        <ExternalLink className="h-3 w-3" />
      </span>
    );
  }
  // No model / no data to reference -> no badge.
  return null;
};

// Disambiguation chips shown when a vague query matches several parts.
// Selecting one asks the agent for that exact part's full details.
const ClarifyOptions = ({ options = [], onSelect, disabled }) => {
  if (!options.length) return null;

  return (
    <div className="mt-2 flex flex-col gap-2">
      {options.map((opt) => {
        const priceLabel = formatPrice(opt.price);
        return (
          <button
            key={opt.part_number}
            type="button"
            disabled={disabled}
            onClick={() =>
              onSelect?.(`Tell me about part ${opt.part_number}`)
            }
            className="group flex items-center justify-between gap-3 rounded-xl border border-ps-border bg-white px-4 py-3 text-left transition-all hover:border-ps-teal/50 hover:bg-ps-tealSoft disabled:cursor-not-allowed disabled:opacity-50"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="truncate text-sm font-semibold text-ps-text">
                  {opt.name || "Replacement Part"}
                </p>
                <FitBadge fits={opt.fits_model} productUrl={opt.product_url} />
              </div>
              <p className="mt-0.5 font-mono text-xs text-ps-teal">
                {opt.part_number}
                {priceLabel && (
                  <span className="ml-2 text-ps-textMuted">{priceLabel}</span>
                )}
              </p>
            </div>
            <ChevronRight className="h-4 w-4 shrink-0 text-ps-textFaint transition-transform group-hover:translate-x-0.5 group-hover:text-ps-teal" />
          </button>
        );
      })}
    </div>
  );
};

export default ClarifyOptions;
