import React from "react";
import { AlertTriangle } from "lucide-react";
import PartCard from "./PartCard";
import RepairGuideCard from "./RepairGuideCard";
import OrderRedirect from "./OrderRedirect";
import MarkdownText from "./MarkdownText";
import ClarifyOptions from "./ClarifyOptions";
import IntentClarifyOptions from "./IntentClarifyOptions";
import FeedbackButtons from "./FeedbackButtons";
import { AVATAR_SRC } from "../../styles/theme";

// Every real agent reply can be rated. We only skip system errors (a failure,
// not an answer quality issue) and the static opening greeting, which has no
// `query` behind it (it wasn't produced in response to a user turn).
const isFeedbackEligible = (message) => {
  if (message.role !== "agent") return false;
  if (message.type === "error") return false;
  const hasContent =
    Boolean(message.content) || (message.parts?.length ?? 0) > 0;
  const isAnswerToUser = Boolean(message.query) || (message.parts?.length ?? 0) > 0;
  return hasContent && isAnswerToUser;
};

const formatTime = (ts) => {
  const d = ts instanceof Date ? ts : new Date(ts);
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
};

const OutOfScope = ({ content }) => (
  <div className="rounded-xl border border-ps-warning/40 bg-ps-warningBg px-4 py-3 text-sm text-ps-text">
    <p className="flex items-start gap-2">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-ps-warning" />
      <span>
        {content ||
          "I can only help with Refrigerator and Dishwasher parts. Can I help you with one of those?"}
      </span>
    </p>
  </div>
);

// Renders any of the agent's structured payloads beneath its text reply.
const AgentExtras = ({ message, modelNumber, onSuggest, isTyping }) => {
  const {
    type,
    parts = [],
    options = [],
    repairSteps = [],
    repairMeta,
    orderUrl,
  } = message;

  if (type === "out_of_scope") return null;

  return (
    <div className="mt-2 space-y-3">
      {type === "clarify" && (
        <ClarifyOptions
          options={options}
          onSelect={onSuggest}
          disabled={isTyping}
        />
      )}

      {type === "intent_clarify" && (
        <IntentClarifyOptions
          options={options}
          onSelect={onSuggest}
          disabled={isTyping}
        />
      )}

      {type === "repair_guide" && (
        <RepairGuideCard
          meta={repairMeta}
          steps={repairSteps}
          parts={parts}
          modelNumber={modelNumber}
        />
      )}

      {(type === "order_redirect" ||
        type === "order_status_redirect" ||
        type === "returns_redirect") && (
        <OrderRedirect type={type} url={orderUrl} />
      )}

      {type !== "repair_guide" &&
        type !== "clarify" &&
        type !== "intent_clarify" &&
        parts.length > 0 &&
        parts.map((part, idx) => (
          <PartCard
            key={part.part_number || idx}
            part={part}
            modelNumber={modelNumber}
          />
        ))}
    </div>
  );
};

const MessageBubble = ({ message, modelNumber, onSuggest, onFeedback, isTyping }) => {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex animate-fadeInUp flex-col items-end">
        {message.image && (
          <img
            src={message.image}
            alt="Uploaded by you"
            className="mb-1 max-h-56 max-w-[85%] rounded-2xl rounded-tr-sm border border-ps-border object-contain sm:max-w-[75%]"
          />
        )}
        {message.content && (
          <div className="max-w-[85%] rounded-2xl rounded-tr-md bg-gradient-to-br from-ps-teal to-ps-tealDark px-5 py-3 text-[15px] font-medium leading-relaxed text-white shadow-[0_4px_14px_-5px_rgba(51,119,120,0.5)] sm:max-w-[75%]">
            {message.content}
          </div>
        )}
        <span className="mr-1 mt-1 text-xs text-ps-textFaint">
          {formatTime(message.timestamp)}
        </span>
      </div>
    );
  }

  const isOutOfScope = message.type === "out_of_scope";
  const isError = message.type === "error";
  const hasPartCard = message.type === "part" && (message.parts?.length ?? 0) > 0;
  // Show the text bubble whenever there's a message. Plain lookups send an
  // empty message (card only); compatibility/answers send text + a card.
  const showTextBubble = Boolean(message.content);

  return (
    <div className="flex animate-fadeInUp gap-2.5">
      <img
        src={AVATAR_SRC}
        alt="PartSelect AI"
        className="h-10 w-10 shrink-0 rounded-full bg-white object-cover shadow-sm ring-1 ring-ps-border"
      />
      <div
        className={`min-w-0 ${hasPartCard ? "max-w-[92%] sm:max-w-[85%]" : "max-w-[85%] sm:max-w-[78%]"}`}
      >
        <span className="mb-1 block text-sm font-semibold text-ps-textMuted">
          PartSelect AI
        </span>

        {isOutOfScope ? (
          <OutOfScope content={message.content} />
        ) : (
          <>
            {showTextBubble && (
              <div
                className={`rounded-2xl rounded-tl-md px-5 py-3.5 ${
                  isError
                    ? "border border-ps-error/40 bg-ps-error/10 text-ps-text"
                    : "border border-ps-border bg-ps-surface text-ps-text shadow-card"
                }`}
              >
                <MarkdownText>{message.content}</MarkdownText>
              </div>
            )}
            <AgentExtras
              message={message}
              modelNumber={modelNumber}
              onSuggest={onSuggest}
              isTyping={isTyping}
            />
            {onFeedback && isFeedbackEligible(message) && (
              <FeedbackButtons
                feedback={message.feedback}
                onSubmit={(score, reason, comment) =>
                  onFeedback(message.id, score, reason, comment)
                }
              />
            )}
          </>
        )}

        <span className="ml-1 mt-1 block text-xs text-ps-textFaint">
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
};

export default MessageBubble;
