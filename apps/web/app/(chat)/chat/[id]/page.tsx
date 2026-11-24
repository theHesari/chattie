import type { UIMessage } from "ai";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { ApiUnavailable } from "@/components/chat/api-unavailable";
import { Chat } from "@/components/chat/chat";
import { getThreadMessages } from "@/lib/api/server";
import { ApiUnavailableError, THREAD_ID_PATTERN } from "@/lib/api/shared";
import type { ChatThreadProps } from "@/types/chat";

export default function ChatPage({ params }: PageProps<"/chat/[id]">) {
  return (
    <Suspense fallback={<ChatSkeleton />}>
      <ChatThread params={params} />
    </Suspense>
  );
}

async function ChatThread({ params }: ChatThreadProps) {
  const { id } = await params;
  if (!THREAD_ID_PATTERN.test(id)) notFound();

  let messages: UIMessage[];
  try {
    messages = await getThreadMessages(id);
  } catch (error) {
    // API down is expected and handled here; anything else (and redirect/notFound) propagates.
    if (error instanceof ApiUnavailableError) return <ApiUnavailable />;
    throw error;
  }
  // `key` resets the chat state when navigating from one thread to another.
  return <Chat key={id} id={id} initialMessages={messages} />;
}

function ChatSkeleton() {
  return (
    <div className="flex h-full items-center justify-center">
      <p className="animate-pulse text-muted-foreground text-sm">
        Loading conversation…
      </p>
    </div>
  );
}
