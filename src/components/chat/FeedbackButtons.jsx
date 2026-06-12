import React, { useState } from "react";
import { ThumbsUp, ThumbsDown, Check } from "lucide-react";

// Preset reasons for a thumbs-down — kept short and product-meaningful so the
// aggregated signal in LangSmith/logs points at a concrete failure mode.
const DOWN_REASONS = [
  "Wrong or unrelated part",
  "Repair steps inaccurate",
  "Didn't answer my question",
  "Incorrect compatibility",
  "Other",
];

const FeedbackButtons = ({ feedback, onSubmit }) => {
  const [showReasons, setShowReasons] = useState(false);
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");

  // Already rated — show a compact confirmation instead of the controls.
  if (feedback) {
    return (
      <div className="mt-2 flex items-center gap-1.5 text-xs font-medium text-ps-textMuted">
        {feedback.score === 1 ? (
          <ThumbsUp className="h-4 w-4 text-ps-success" />
        ) : (
          <ThumbsDown className="h-4 w-4 text-ps-warning" />
        )}
        <span>Thanks for the feedback</span>
      </div>
    );
  }

  // Allow submitting with a preset reason, a typed comment, or both — so typing
  // detail alone is enough (the user shouldn't be forced to pick a chip).
  const canSubmit = Boolean(reason) || Boolean(comment.trim());

  const submitDown = () => {
    if (!canSubmit) return;
    onSubmit(0, reason, comment.trim());
    setShowReasons(false);
  };

  return (
    <div className="mt-2.5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-ps-textMuted">
          Was this helpful?
        </span>
        <button
          type="button"
          onClick={() => onSubmit(1)}
          aria-label="Helpful"
          title="Helpful"
          className="inline-flex items-center gap-1.5 rounded-full border border-ps-border bg-white px-3 py-1.5 text-xs font-semibold text-ps-textMuted shadow-sm transition-colors hover:border-ps-success/50 hover:bg-ps-success/10 hover:text-ps-success"
        >
          <ThumbsUp className="h-4 w-4" />
          Yes
        </button>
        <button
          type="button"
          onClick={() => setShowReasons((v) => !v)}
          aria-label="Not helpful"
          title="Not helpful"
          aria-expanded={showReasons}
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition-colors hover:border-ps-error/50 hover:bg-ps-error/10 hover:text-ps-error ${
            showReasons
              ? "border-ps-error/50 bg-ps-error/10 text-ps-error"
              : "border-ps-border bg-white text-ps-textMuted"
          }`}
        >
          <ThumbsDown className="h-4 w-4" />
          No
        </button>
      </div>

      {showReasons && (
        <div className="mt-2 w-full max-w-sm animate-fadeInUp rounded-xl border border-ps-border bg-white p-3 shadow-card">
          <p className="mb-2 text-xs font-semibold text-ps-textMuted">
            What went wrong?
          </p>
          <div className="flex flex-wrap gap-1.5">
            {DOWN_REASONS.map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setReason(r)}
                className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                  reason === r
                    ? "border-ps-teal bg-ps-tealSoft font-semibold text-ps-teal"
                    : "border-ps-border text-ps-textMuted hover:border-ps-teal/50"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value.slice(0, 300))}
            rows={4}
            placeholder="Tell us what went wrong (optional)…"
            className="mt-2 min-h-[5.5rem] w-full resize-y rounded-lg border border-ps-border bg-white px-3 py-2 text-sm leading-relaxed text-ps-text shadow-inner outline-none focus:border-ps-teal focus:ring-2 focus:ring-ps-teal/20"
          />
          <div className="mt-1 text-right text-[11px] text-ps-textFaint">
            {comment.length}/300
          </div>
          <div className="mt-2 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setShowReasons(false)}
              className="rounded-lg px-2.5 py-1 text-xs font-medium text-ps-textMuted hover:text-ps-text"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={submitDown}
              disabled={!canSubmit}
              className="inline-flex items-center gap-1 rounded-lg bg-ps-teal px-3 py-1 text-xs font-semibold text-white transition-colors hover:bg-ps-tealDark disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Check className="h-3.5 w-3.5" />
              Submit
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default FeedbackButtons;
