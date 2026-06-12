import React from "react";
import { CheckCircle2, XCircle, Clock } from "lucide-react";

// Status pill. Defaults to the green/red "ok" model (compatible / in stock),
// but also supports an explicit `tone` for the in-between "warn" state used by
// orderable-but-not-stocked parts (e.g. Special Order).
const TONES = {
  success: {
    cls: "bg-ps-success/10 text-ps-success ring-ps-success/20",
    Icon: CheckCircle2,
  },
  error: {
    cls: "bg-ps-error/10 text-ps-error ring-ps-error/20",
    Icon: XCircle,
  },
  warn: {
    cls: "bg-ps-warningBg text-ps-warning ring-ps-warning/20",
    Icon: Clock,
  },
};

const CompatibilityBadge = ({ ok = true, tone, children }) => {
  const resolved = tone || (ok ? "success" : "error");
  const { cls, Icon } = TONES[resolved] || TONES.success;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ${cls}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {children}
    </span>
  );
};

export default CompatibilityBadge;
