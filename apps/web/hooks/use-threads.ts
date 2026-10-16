import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchThreads } from "@/lib/api/client";
import { threadsKey } from "@/lib/queries/threads";

/** The signed-in user's threads. Seeded by the server; refetched when invalidated. */
export function useThreads() {
  return useSuspenseQuery({ queryKey: threadsKey, queryFn: fetchThreads });
}
