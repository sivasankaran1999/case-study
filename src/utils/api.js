// API client for the PartSelect AI Chat Agent backend.
//
// The backend is expected to expose a POST /chat endpoint that accepts the
// user message, an optional saved model number, and the prior conversation
// history. It responds with the shape documented in API_RESPONSE_SHAPE below.

const API_BASE = process.env.REACT_APP_API_BASE || "http://localhost:8000";

// Hard ceiling on a single chat request. A turn that needs a live web scrape
// (e.g. an unindexed part number) is the slow path; anything beyond this is
// treated as a failure so the UI surfaces an error instead of spinning forever.
const REQUEST_TIMEOUT_MS = 90000;

/**
 * Expected response shape from POST /chat:
 * {
 *   message: string,
 *   type: "text" | "part" | "repair_guide" | "clarify" | "intent_clarify" | "order_redirect"
 *       | "order_status_redirect" | "returns_redirect" | "out_of_scope",
 *   parts: Array<{
 *     part_number, name, price, in_stock, image_url, product_url, compatible_with,
 *     description, fixes_symptoms, installation_steps, video_url
 *   }>,
 *   options: Array,  // part choices (clarify) or action choices (intent_clarify)
 *   repair_steps: Array<{ step_number, instruction }>,
 *   repair_meta: { title, time_estimate, difficulty } | null,
 *   url: string | null,  // PartSelect redirect for order_redirect / order_status_redirect
 *   confidence: number
 * }
 */

export const sendMessage = async (
  message,
  modelNumber,
  history = [],
  image = null
) => {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response;
  try {
    response = await fetch(`${API_BASE}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        model_number: modelNumber || null,
        conversation_history: history,
        image: image || null,
      }),
      signal: controller.signal,
    });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error("Chat request timed out");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    throw new Error(`Chat request failed with status ${response.status}`);
  }

  return response.json();
};

/**
 * Submit 👍/👎 feedback on an agent answer.
 * @param {Object} fb
 * @param {number} fb.score        1 (up) or 0 (down)
 * @param {string|null} fb.traceId LangSmith run id from the /chat response
 * @param {string} [fb.requestId]
 * @param {string} [fb.reason]     preset reason (thumbs-down)
 * @param {string} [fb.comment]    optional free text
 * @param {string} [fb.query]      the user message that produced the answer
 * @param {string} [fb.intent]     response type / intent for grouping
 * Best-effort: never throws to the UI.
 */
export const submitFeedback = async ({
  score,
  traceId = null,
  requestId = null,
  reason = "",
  comment = "",
  query = "",
  intent = "",
}) => {
  try {
    const response = await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        score,
        trace_id: traceId,
        request_id: requestId,
        reason,
        comment,
        query,
        intent,
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
};

const api = { sendMessage, submitFeedback };
export default api;
