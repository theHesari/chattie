"use client";

import Link from "next/link";
import { useActiveThreadId } from "@/hooks/use-active-thread-id";
import { cn } from "@/lib/utils";
import type { ThreadListProps } from "@/types/thread";

export function ThreadList({ threads }: ThreadListProps) {
  const activeId = useActiveThreadId();

  if (threads.length === 0) {
    return (
      <p className="px-2 py-1 text-muted-foreground text-sm">No chats yet</p>
    );
  }

  return (
    <ul className="flex flex-col gap-0.5">
      {threads.map((thread) => {
        const isActive = thread.id === activeId;
        return (
          <li key={thread.id}>
            <Link
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "block truncate rounded-md px-2 py-1.5 text-sm hover:bg-accent",
                isActive && "bg-accent font-medium",
              )}
              href={`/chat/${thread.id}`}
              title={thread.title}
            >
              {thread.title}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
