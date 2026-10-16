"use client";

import { ArrowDownIcon } from "lucide-react";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import { Button } from "@/components/ui/button";
import type { ConversationProps } from "@/types/chat";

/** Scrollable message log that stays pinned to the newest message. */
export function Conversation({ children }: ConversationProps) {
  return (
    <StickToBottom
      className="relative min-h-0 flex-1 overflow-y-hidden"
      initial="smooth"
      resize="smooth"
      role="log"
    >
      <StickToBottom.Content className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 pt-10 pb-4">
        {children}
      </StickToBottom.Content>
      <ScrollToBottomButton />
    </StickToBottom>
  );
}

function ScrollToBottomButton() {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();
  if (isAtBottom) return null;

  return (
    <Button
      aria-label="Scroll to latest message"
      className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full"
      onClick={() => scrollToBottom()}
      size="icon"
      variant="outline"
    >
      <ArrowDownIcon />
    </Button>
  );
}
