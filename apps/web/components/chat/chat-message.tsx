import { Streamdown } from "streamdown";
import { ToolCard } from "@/components/chat/tool-card";
import { cn } from "@/lib/utils";
import type { ChatMessageProps } from "@/types/chat";

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div
      data-role={message.role}
      className={cn(
        "flex flex-col gap-3",
        isUser ? "items-end" : "items-start",
      )}
    >
      {message.parts.map((part, index) => {
        const key = `${message.id}-${index}`;
        switch (part.type) {
          case "text":
            return isUser ? (
              <p
                key={key}
                className="max-w-[80%] whitespace-pre-wrap rounded-2xl bg-secondary px-4 py-2"
              >
                {part.text}
              </p>
            ) : (
              <Streamdown
                key={key}
                className="w-full"
                isAnimating={isStreaming}
              >
                {part.text}
              </Streamdown>
            );
          case "dynamic-tool":
            return <ToolCard key={key} part={part} />;
          default:
            return null;
        }
      })}
    </div>
  );
}
