"use client";

import { PlusIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useNewChat } from "@/hooks/use-new-chat";

export function NewChatButton() {
  const startNewChat = useNewChat();

  return (
    <Button onClick={startNewChat} size="sm" type="button" variant="ghost">
      <PlusIcon />
      New chat
    </Button>
  );
}
