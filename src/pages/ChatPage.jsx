import React from "react";
import ChatHeader from "../components/chat/ChatHeader";
import ChatWindow from "../components/chat/ChatWindow";
import useChat from "../hooks/useChat";
import useModelMemory from "../hooks/useModelMemory";

const ChatPage = () => {
  const { modelNumber, saveModel, clearModel } = useModelMemory();
  const { messages, isTyping, showChips, sendMessage, sendFeedback } = useChat(
    modelNumber,
    saveModel
  );

  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-ps-bg">
      {/* Subtle brand-tinted ambiance: a couple of soft, low-opacity blobs on a
          clean white base. Restrained so the UI reads crisp, not hazy. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 overflow-hidden"
      >
        <div className="absolute -left-40 -top-48 h-[30rem] w-[30rem] rounded-full bg-ps-teal/[0.07] blur-3xl animate-auroraDrift" />
        <div className="absolute -right-32 top-8 h-[26rem] w-[26rem] rounded-full bg-ps-gold/[0.06] blur-3xl animate-auroraDriftSlow" />
        <div className="absolute -bottom-48 left-1/4 h-[34rem] w-[34rem] rounded-full bg-ps-teal/[0.05] blur-3xl animate-auroraDrift" />
      </div>

      <div className="relative z-10 flex min-h-0 flex-1 flex-col">
        <ChatHeader
          modelNumber={modelNumber}
          onSaveModel={saveModel}
          onClearModel={clearModel}
        />
        <ChatWindow
          messages={messages}
          isTyping={isTyping}
          showChips={showChips}
          sendMessage={sendMessage}
          sendFeedback={sendFeedback}
          modelNumber={modelNumber}
          saveModel={saveModel}
        />
      </div>
    </div>
  );
};

export default ChatPage;
