import { Suspense } from "react";
import { NewChatButton } from "@/components/sidebar/new-chat-button";
import { ThreadList } from "@/components/sidebar/thread-list";
import { getThreads } from "@/lib/api";
import type { SidebarMessageProps } from "@/types/sidebar";

/** Brand, "New chat" and thread history; shared by the desktop sidebar and the mobile drawer. */
export function SidebarContent() {
  return (
    <>
      <div className="flex items-center justify-between px-3 pt-4 pb-2">
        <span className="font-semibold">Chattie</span>
        <NewChatButton />
      </div>
      <nav
        aria-label="Chats"
        className="min-h-0 flex-1 overflow-y-auto px-2 pt-3 pb-2"
      >
        <Suspense fallback={<SidebarMessage text="Loading chats…" />}>
          <Threads />
        </Suspense>
      </nav>
    </>
  );
}

async function Threads() {
  try {
    return <ThreadList threads={await getThreads()} />;
  } catch {
    // The chat itself stays usable even if the history can't be listed.
    return <SidebarMessage text="Couldn't load chats" />;
  }
}

function SidebarMessage({ text }: SidebarMessageProps) {
  return <p className="px-2 py-1 text-muted-foreground text-sm">{text}</p>;
}
