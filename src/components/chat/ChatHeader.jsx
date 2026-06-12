import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Pencil, Check, X, Plus } from "lucide-react";
import Logo from "../Logo";

const ChatHeader = ({ modelNumber, onSaveModel, onClearModel }) => {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(modelNumber || "");

  const commit = () => {
    const trimmed = value.trim();
    if (trimmed) onSaveModel(trimmed);
    setEditing(false);
  };

  return (
    <header className="z-20 border-b border-ps-border bg-ps-bg/80 backdrop-blur-md">
      {/* Mirrors the landing navbar exactly so the logo placement + size do not
          shift when navigating between the two pages. */}
      <div className="mx-auto flex h-20 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center" aria-label="Back to home">
          <Logo size="lg" showAI={false} />
        </Link>

        <div className="flex shrink-0 items-center gap-3">
          {editing ? (
            <div className="flex items-center gap-1">
              <input
                autoFocus
                value={value}
                onChange={(e) => setValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit();
                  if (e.key === "Escape") setEditing(false);
                }}
                placeholder="Model #"
                className="w-32 rounded-md border border-ps-border bg-ps-elevated px-2 py-1 text-xs text-ps-text outline-none focus:border-ps-teal"
              />
              <button
                onClick={commit}
                aria-label="Save model number"
                className="flex h-7 w-7 items-center justify-center rounded-md bg-ps-teal text-white hover:bg-ps-tealDark"
              >
                <Check className="h-4 w-4" />
              </button>
            </div>
          ) : modelNumber ? (
            <div className="hidden items-center gap-1 sm:flex">
              <button
                onClick={() => {
                  setValue(modelNumber);
                  setEditing(true);
                }}
                className="inline-flex items-center gap-1.5 rounded-full border border-ps-border bg-ps-surface px-3 py-1 text-xs font-medium text-ps-text transition-colors hover:border-ps-teal/50"
                title="Edit model number"
              >
                <span className="text-ps-textMuted">Model:</span>
                <span className="font-mono font-semibold">{modelNumber}</span>
                <Pencil className="h-3 w-3 text-ps-textMuted" />
              </button>
              <button
                onClick={onClearModel}
                aria-label="Clear saved model"
                className="flex h-7 w-7 items-center justify-center rounded-full text-ps-textMuted transition-colors hover:bg-ps-surface hover:text-ps-error"
                title="Clear model (stops using it for fit checks)"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          ) : (
            <button
              onClick={() => {
                setValue("");
                setEditing(true);
              }}
              className="inline-flex items-center gap-1.5 rounded-full border border-ps-teal/40 bg-ps-tealSoft px-4 py-2 text-sm font-semibold text-ps-teal transition-colors hover:border-ps-teal hover:bg-ps-teal hover:text-white"
              title="Add your appliance model number"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">Add model</span>
              <span className="sm:hidden">Model</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
};

export default ChatHeader;
