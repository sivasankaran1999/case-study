import React, { useEffect, useRef, useState } from "react";
import { Send, ImagePlus, X, ArrowDown, Sparkles } from "lucide-react";
import MessageBubble from "./MessageBubble";
import TypingIndicator from "./TypingIndicator";
import SuggestionChips from "./SuggestionChips";
import ModelNumberBanner from "./ModelNumberBanner";

const MAX_CHARS = 500;
const MAX_IMAGE_DIM = 1280; // downscale large photos before upload
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/webp"];

const sanitizeInput = (text) =>
  text
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/\r\n/g, "\n")
    .slice(0, MAX_CHARS);

// Read a File into a downscaled JPEG data URL to keep the upload payload small.
const fileToDataUrl = (file) =>
  new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("read failed"));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("decode failed"));
      img.onload = () => {
        const scale = Math.min(
          1,
          MAX_IMAGE_DIM / Math.max(img.width, img.height)
        );
        const w = Math.round(img.width * scale);
        const h = Math.round(img.height * scale);
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });

const ChatWindow = ({
  messages,
  isTyping,
  showChips,
  sendMessage,
  sendFeedback,
  modelNumber,
  saveModel,
}) => {
  const [input, setInput] = useState("");
  const [image, setImage] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [showScrollBtn, setShowScrollBtn] = useState(false);
  const endRef = useRef(null);
  const scrollRef = useRef(null);
  const textareaRef = useRef(null);
  const fileInputRef = useRef(null);

  const resizeTextarea = () => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;
  };

  const scrollToBottom = () =>
    endRef.current?.scrollIntoView({ behavior: "smooth" });

  // Reveal the "jump to latest" button only when the user has scrolled up
  // meaningfully from the bottom of the conversation.
  const handleScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setShowScrollBtn(distanceFromBottom > 240);
  };

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  useEffect(() => {
    resizeTextarea();
  }, [input]);

  const handleInputChange = (value) => {
    setInput(sanitizeInput(value));
  };

  const handlePaste = (e) => {
    e.preventDefault();
    const pasted = e.clipboardData.getData("text/plain") || "";
    const cleaned = sanitizeInput(pasted);
    const el = e.currentTarget;
    const start = el.selectionStart ?? input.length;
    const end = el.selectionEnd ?? input.length;
    const next = sanitizeInput(
      input.slice(0, start) + cleaned + input.slice(end)
    );
    setInput(next);
    requestAnimationFrame(() => {
      const pos = Math.min(start + cleaned.length, next.length);
      el.setSelectionRange(pos, pos);
      resizeTextarea();
    });
  };

  const handleFile = async (file) => {
    setUploadError("");
    if (!file) return;
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setUploadError("Please upload a JPG, PNG, or WebP image.");
      return;
    }
    try {
      const dataUrl = await fileToDataUrl(file);
      setImage(dataUrl);
    } catch {
      setUploadError("Couldn't read that image. Try another one.");
    }
  };

  const handleSend = () => {
    const text = input.trim();
    if ((!text && !image) || isTyping) return;
    sendMessage(text, image);
    setInput("");
    setImage(null);
    setUploadError("");
    requestAnimationFrame(resizeTextarea);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-transparent">
      {/* Scrollable conversation */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="relative min-h-0 flex-1 overflow-y-auto scrollbar-thin"
      >
        <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6 sm:px-10">
          {showChips ? (
            // Empty state: a landing-page-style intro, then the model box + chips.
            <div className="flex flex-col items-center gap-7 py-6 text-center sm:py-10">
              <div className="flex flex-col items-center">
                <span className="inline-flex items-center gap-2 rounded-full border border-ps-border bg-white px-3.5 py-1.5 text-sm font-semibold text-ps-teal shadow-sm">
                  <Sparkles className="h-4 w-4 text-ps-gold" />
                  AI assistant for appliance parts
                </span>

                <h2 className="mt-6 text-3xl font-extrabold leading-[1.08] tracking-tight text-ps-text sm:text-4xl">
                  Expert Guidance for
                  <br />
                  <span className="relative text-ps-teal">
                    Every Repair.
                    <span className="absolute -bottom-1 left-0 h-1.5 w-full rounded-full bg-ps-gold/70" />
                  </span>
                </h2>

                <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-ps-textMuted">
                  Intelligent help for{" "}
                  <span className="font-semibold text-ps-text">Refrigerator</span>{" "}
                  and{" "}
                  <span className="font-semibold text-ps-text">Dishwasher</span>{" "}
                  parts — instant answers, smart troubleshooting, and
                  compatibility checks.
                </p>
              </div>

              <div className="w-full max-w-4xl space-y-3">
                {!modelNumber && <ModelNumberBanner onSave={saveModel} />}
                <SuggestionChips onSelect={sendMessage} disabled={isTyping} />
              </div>
            </div>
          ) : (
            <>
                      {messages.map((message) => (
                        <MessageBubble
                          key={message.id}
                          message={message}
                          modelNumber={modelNumber}
                          onSuggest={sendMessage}
                          onFeedback={sendFeedback}
                          isTyping={isTyping}
                        />
                      ))}

              {isTyping && <TypingIndicator />}
            </>
          )}

          <div ref={endRef} />
        </div>

        {/* Jump to latest — sticks to the bottom of the viewport while scrolled up */}
        <div className="pointer-events-none sticky bottom-4 z-10 mx-auto flex max-w-7xl justify-end px-4 sm:px-10">
          {showScrollBtn && (
            <button
              type="button"
              onClick={scrollToBottom}
              aria-label="Scroll to latest message"
              className="pointer-events-auto flex h-10 w-10 animate-fadeInUp items-center justify-center rounded-full border border-ps-border bg-ps-surface text-ps-teal shadow-cardHover transition-all hover:bg-ps-tealSoft active:scale-90"
            >
              <ArrowDown className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>

      {/* Composer — solid surface + elevated pill so it clearly stands out */}
      <div className="border-t border-ps-border bg-ps-bg shadow-[0_-10px_30px_-18px_rgba(31,75,76,0.35)]">
        <div className="mx-auto max-w-7xl px-4 pb-4 pt-3 sm:px-10">
          {image && (
            <div className="mb-2 inline-flex items-center gap-2 rounded-xl border border-ps-border bg-ps-elevated p-1.5">
              <img
                src={image}
                alt="Upload preview"
                className="h-14 w-14 rounded-lg object-cover"
              />
              <button
                type="button"
                onClick={() => setImage(null)}
                aria-label="Remove image"
                className="flex h-6 w-6 items-center justify-center rounded-full text-ps-textMuted transition-colors hover:bg-ps-surface hover:text-ps-error"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          )}
          {uploadError && (
            <p className="mb-2 text-xs font-medium text-ps-error">
              {uploadError}
            </p>
          )}
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            className="hidden"
            onChange={(e) => {
              handleFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <div className="flex items-end gap-1.5 rounded-[1.6rem] border border-ps-borderStrong bg-white p-2 shadow-[0_6px_24px_-8px_rgba(31,75,76,0.25)] transition-all focus-within:border-ps-teal focus-within:shadow-[0_8px_28px_-8px_rgba(51,119,120,0.4)] focus-within:ring-2 focus-within:ring-ps-teal/20">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isTyping}
              aria-label="Upload a photo"
              title="Upload a photo (model label, part, error code, wiring)"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-ps-textMuted transition-colors hover:bg-ps-tealSoft hover:text-ps-teal disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ImagePlus className="h-[22px] w-[22px]" />
            </button>
            <textarea
              ref={textareaRef}
              value={input}
              rows={1}
              maxLength={MAX_CHARS}
              disabled={isTyping}
              onChange={(e) => handleInputChange(e.target.value)}
              onInput={(e) => handleInputChange(e.target.value)}
              onPaste={handlePaste}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Ask about parts, repairs, or compatibility…"
              spellCheck
              autoComplete="off"
              className="max-h-36 min-h-[2.75rem] w-full resize-none self-center overflow-y-auto bg-transparent px-1.5 py-2 text-base leading-relaxed text-ps-text caret-ps-teal outline-none placeholder:text-ps-textMuted/80 disabled:opacity-60"
            />
            <button
              type="button"
              onClick={handleSend}
              disabled={isTyping || (!input.trim() && !image)}
              aria-label="Send message"
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-ps-teal to-ps-tealDark text-white shadow-sm transition-all hover:shadow-glow active:scale-90 disabled:cursor-not-allowed disabled:from-ps-borderStrong disabled:to-ps-borderStrong disabled:text-white/70 disabled:shadow-none disabled:active:scale-100"
            >
              <Send className="h-5 w-5" />
            </button>
          </div>
          <div className="mt-2 flex items-center justify-between px-2 text-xs text-ps-textFaint">
            <span>
              Press <kbd className="font-sans font-semibold text-ps-textMuted">Enter</kbd> to send ·{" "}
              <kbd className="font-sans font-semibold text-ps-textMuted">Shift + Enter</kbd> for a new line
            </span>
            <span className="font-mono">
              {input.length}/{MAX_CHARS}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatWindow;
