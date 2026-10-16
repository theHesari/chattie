"use client";

import { MessageSquareIcon } from "lucide-react";
import { ChatMessage } from "@/components/chat/chat-message";
import { Conversation } from "@/components/chat/conversation";
import { PromptForm } from "@/components/chat/prompt-form";
import { Suggestions } from "@/components/chat/suggestions";
import { useChatSession } from "@/hooks/use-chat-session";
import type { ChatProps } from "@/types/chat";

const SUGGESTIONS = [
  "What's the weather in Tehran today?",
  "What day is it today?",
  "Will it rain in Paris tomorrow?",
] as const;

export function Chat(props: ChatProps) {
  const { messages, status, error, isBusy, send, stop } = useChatSession(props);
  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      <Conversation>
        {isEmpty && <EmptyState />}
        {messages.map((message, index) => (
          <ChatMessage
            key={message.id}
            message={message}
            isStreaming={
              status === "streaming" && index === messages.length - 1
            }
          />
        ))}
        {status === "submitted" && (
          <p className="animate-pulse text-muted-foreground text-sm">
            Thinking…
          </p>
        )}
        {error && (
          <p role="alert" className="text-destructive text-sm">
            Something went wrong. Please try again.
          </p>
        )}
      </Conversation>

      <div className="mx-auto flex w-full max-w-3xl flex-col gap-3 p-4">
        {isEmpty && <Suggestions suggestions={SUGGESTIONS} onSelect={send} />}
        <PromptForm isBusy={isBusy} onSubmit={send} onStop={stop} />
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 py-24 text-center">
      <MessageSquareIcon className="size-10 text-muted-foreground" />
      <h2 className="font-medium">Start a conversation</h2>
      <p className="text-muted-foreground text-sm">
        Ask about the weather, today's date, or anything else.
      </p>
    </div>
  );
}
