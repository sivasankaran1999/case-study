import { useCallback, useRef, useState } from "react";
import {
  sendMessage as apiSendMessage,
  submitFeedback as apiSubmitFeedback,
} from "../utils/api";

const WELCOME_MESSAGE = {
  id: 1,
  role: "agent",
  type: "text",
  content:
    "Hi! I'm the **PartSelect AI assistant** — here to help with **Refrigerator and Dishwasher** parts and repairs. How can I help you today?",
  timestamp: new Date(),
};

// Builds the compact conversation history the backend expects.
const toHistory = (messages) =>
  messages.map((m) => ({
    role: m.role === "agent" ? "assistant" : "user",
    content: m.content,
  }));

const useChat = (modelNumber, saveModel) => {
  const [messages, setMessages] = useState([WELCOME_MESSAGE]);
  const [isTyping, setIsTyping] = useState(false);
  const [showChips, setShowChips] = useState(true);
  const idRef = useRef(2);

  const nextId = () => idRef.current++;

  const sendMessage = useCallback(
    async (text, image = null) => {
      const trimmed = (text || "").trim();
      // Allow an image-only message (e.g. a photo of the model label).
      if ((!trimmed && !image) || isTyping) return;

      const userMessage = {
        id: nextId(),
        role: "user",
        type: "text",
        content: trimmed,
        image: image || null,
        timestamp: new Date(),
      };

      // Snapshot history (before this message) for the API call.
      let history = [];
      setMessages((prev) => {
        history = toHistory(prev);
        return [...prev, userMessage];
      });

      setShowChips(false);
      setIsTyping(true);

      try {
        const res = await apiSendMessage(trimmed, modelNumber, history, image);

        // Keep header model in sync when the user states a new model in chat.
        if (res?.model_number && saveModel) {
          saveModel(res.model_number);
        }

        const agentMessage = {
          id: nextId(),
          role: "agent",
          type: res?.type || "text",
          content: res?.message || "",
          parts: res?.parts || [],
          options: res?.options || [],
          repairSteps: res?.repair_steps || [],
          repairMeta: res?.repair_meta || null,
          orderUrl: res?.url || null,
          confidence: typeof res?.confidence === "number" ? res.confidence : null,
          traceId: res?.trace_id || null,
          requestId: res?.request_id || null,
          query: trimmed,
          feedback: null,
          timestamp: new Date(),
        };

        setMessages((prev) => [...prev, agentMessage]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "agent",
            type: "error",
            content:
              "Sorry — I couldn't reach the assistant just now. Please make sure the backend is running and try again.",
            timestamp: new Date(),
          },
        ]);
      } finally {
        setIsTyping(false);
      }
    },
    [isTyping, modelNumber, saveModel]
  );

  // Record 👍/👎 on an agent message. Optimistically marks the bubble as rated
  // and fires the API call; the backend handles LangSmith + logging.
  const sendFeedback = useCallback((messageId, score, reason = "", comment = "") => {
    let target = null;
    setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== messageId) return m;
        target = m;
        return { ...m, feedback: { score, reason, comment } };
      })
    );
    if (target) {
      apiSubmitFeedback({
        score,
        traceId: target.traceId,
        requestId: target.requestId,
        reason,
        comment,
        query: target.query || "",
        intent: target.type || "",
      });
    }
  }, []);

  return { messages, isTyping, showChips, sendMessage, sendFeedback };
};

export default useChat;
