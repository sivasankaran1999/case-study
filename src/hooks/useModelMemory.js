import { useCallback, useState } from "react";

const STORAGE_KEY = "ps_model_number";

// Remembers the appliance model number in sessionStorage (survives page
// refresh; clears when the browser tab is closed). Sent with every chat
// request for compatibility checks and fit badges.
const useModelMemory = () => {
  const [modelNumber, setModelNumber] = useState(() => {
    try {
      return sessionStorage.getItem(STORAGE_KEY) || null;
    } catch {
      return null;
    }
  });

  const saveModel = useCallback((model) => {
    const normalized = (model || "").toUpperCase().trim();
    if (!normalized) return;
    setModelNumber(normalized);
    try {
      sessionStorage.setItem(STORAGE_KEY, normalized);
    } catch {
      /* sessionStorage unavailable — keep in-memory only */
    }
  }, []);

  const clearModel = useCallback(() => {
    setModelNumber(null);
    try {
      sessionStorage.removeItem(STORAGE_KEY);
    } catch {
      /* no-op */
    }
  }, []);

  return { modelNumber, saveModel, clearModel };
};

export default useModelMemory;
