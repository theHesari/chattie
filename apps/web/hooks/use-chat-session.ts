import { useChat } from "@ai-sdk/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createChatTransport } from "@/lib/api";
import type { ChatProps } from "@/types/chat";

/** One chat thread: streamed messages from the API plus send/stop actions. */
export function useChatSession({ id, initialMessages }: ChatProps) {
  const router = useRouter();
  const [transport] = useState(createChatTransport);
  const { messages, sendMessage, status, stop, error } = useChat({
    id,
    messages: initialMessages,
    transport,
    // Re-render server components so the sidebar shows this thread at the top.
    onFinish: () => router.refresh(),
  });

  const isBusy = status === "submitted" || status === "streaming";

  const send = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isBusy) return;
    sendMessage({ text: trimmed });
  };

  return { messages, status, error, isBusy, send, stop };
}
