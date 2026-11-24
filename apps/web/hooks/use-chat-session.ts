import { useChat } from "@ai-sdk/react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { createChatTransport } from "@/lib/api/client";
import { threadsKey } from "@/lib/queries/threads";
import type { ChatProps } from "@/types/chat";

/** One chat thread: streamed messages from the API plus send/stop actions. */
export function useChatSession({ id, initialMessages }: ChatProps) {
  const queryClient = useQueryClient();
  const [transport] = useState(createChatTransport);
  const { messages, sendMessage, regenerate, status, stop, error } = useChat({
    id,
    messages: initialMessages,
    transport,
    // A reply creates the thread or bumps it to the top: refetch the sidebar list.
    onFinish: () => queryClient.invalidateQueries({ queryKey: threadsKey }),
  });

  const isBusy = status === "submitted" || status === "streaming";

  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isBusy) return;
    sendMessage({ text: trimmed });
  };

  // After a failed send the last message is the unanswered user message; regenerate()
  // sends it again (same id, so the server never stores it twice).
  const retry = () => regenerate();

  return { messages, status, error, isBusy, send, stop, retry };
}
